import logging
from logging.handlers import RotatingFileHandler
import asyncio
from datetime import datetime

import httpx
from fastapi import APIRouter, status, HTTPException, Depends, Response, Request
from sqlalchemy.orm import Session

from database import get_db
import model
from rate_limiting import limiter
from schemas.visit_note_schema import VisitNoteBase, VisitNoteDetail

router = APIRouter(tags=["Visit Notes"])

logger = logging.getLogger("phr_api_visit_note")
logger.setLevel(logging.INFO)   
handler = RotatingFileHandler(
    r"logs/visit_note.log", 
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=2
)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'))
logger.addHandler(handler)

def _parse_recorded_at(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="recorded_at must be a valid ISO datetime")

def _serialize_vital(vital: model.Vitals) -> dict:
    return {
        "vital_id": vital.vital_id,
        "type": vital.type,
        "systolic": vital.systolic,
        "diastolic": vital.diastolic,
        "value": vital.value,
        "unit": vital.unit,
        "meal_time": vital.meal_time,
        "recorded_at": vital.recorded_at.isoformat(),
    }

async def _send_to_engine(data: dict, url: str, system_id: str):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            headers = {"Content-Type": "application/json", "System-Id": system_id}
            response = await client.post(url, json=data, headers=headers)
            if response.status_code in (200, 201, 202, 203, 204):
                return

            try:
                detail = response.json().get("detail", f"Engine returned {response.status_code}")
            except Exception:
                detail = response.text or f"Engine returned {response.status_code}"
            logger.error(f"Engine rejected vitals payload: {detail}")
    except Exception as exp:
        logger.error(f"Failed to send vitals to engine: {str(exp)}")

def _vital_observation(vital: model.Vitals, patient_nic: str, doctor_id: str, hospital_id: str) -> dict:
    observation = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"text": vital.type},
        "subject": {"reference": f"Patient/{patient_nic}"},
        "performer": [{"reference": f"Practitioner/{doctor_id}"}],
        "effectiveDateTime": vital.recorded_at.isoformat(),
        "extension": [
            {
                "url": "hospital-id",
                "valueString": hospital_id,
            }
        ],
    }

    if vital.type.lower() == "bp":
        observation["component"] = [
            {
                "code": {"text": "Systolic"},
                "valueQuantity": {"value": vital.systolic, "unit": vital.unit},
            },
            {
                "code": {"text": "Diastolic"},
                "valueQuantity": {"value": vital.diastolic, "unit": vital.unit},
            },
        ]
    else:
        observation["valueQuantity"] = {
            "value": vital.value,
            "unit": vital.unit,
        }
        if vital.meal_time:
            observation["note"] = [{"text": vital.meal_time}]

    return observation

@router.post("/add-vitals", status_code=status.HTTP_201_CREATED)
async def add_vitals(request: Request, db: Session = Depends(get_db)):
    """
        Store a list of patient vital readings.
    """
    try:
        payload = await request.json()
        vitals_data = payload.get("vitals", payload) if isinstance(payload, dict) else payload

        if not isinstance(vitals_data, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request body must be a list of vitals")

        vitals = []
        for vital_data in vitals_data:
            if not isinstance(vital_data, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each vital must be an object")

            missing_fields = [field for field in ("type", "unit", "recorded_at") if vital_data.get(field) is None]
            if missing_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required vital field(s): {', '.join(missing_fields)}"
                )

            vitals.append(model.Vitals(
                type=str(vital_data["type"]),
                systolic=None if vital_data.get("systolic") is None else str(vital_data.get("systolic")),
                diastolic=None if vital_data.get("diastolic") is None else str(vital_data.get("diastolic")),
                value=None if vital_data.get("value") is None else str(vital_data.get("value")),
                unit=str(vital_data["unit"]),
                meal_time=None if vital_data.get("meal_time") is None else str(vital_data.get("meal_time")),
                recorded_at=_parse_recorded_at(vital_data["recorded_at"]),
            ))

        db.add_all(vitals)
        db.commit()
        for vital in vitals:
            db.refresh(vital)

        return {
            "message": "Vitals added successfully",
            "vitals": [_serialize_vital(vital) for vital in vitals],
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exp:
        db.rollback()
        logger.error(f"Error adding vitals: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.get("/vitals", status_code=status.HTTP_200_OK)
def get_vitals(db: Session = Depends(get_db)):
    """
        Retrieve all stored vital readings.
    """
    try:
        vitals = db.query(model.Vitals).order_by(model.Vitals.recorded_at.desc()).all()
        return [_serialize_vital(vital) for vital in vitals]
    except Exception as exp:
        logger.error(f"Error fetching vitals: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.post("/vitals/send-to-engine", status_code=status.HTTP_200_OK)
async def send_vitals_to_engine(request: Request, db: Session = Depends(get_db)):
    """
        Send stored vital readings to the InterfaceEngine as a compact FHIR Bundle.
    """
    try:
        payload = await request.json()
        patient_nic = str(payload.get("patient_nic", "")).strip()
        doctor_id = str(payload.get("doctor_id", "")).strip()
        hospital_id = str(payload.get("hospital_id", "")).strip()

        if not patient_nic or not doctor_id or not hospital_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_nic, doctor_id, and hospital_id are required"
            )

        vitals = db.query(model.Vitals).order_by(model.Vitals.recorded_at.desc()).all()
        fhir_msg = {
            "resourceType": "Bundle",
            "type": "message",
            "identifier": {
                "value": hospital_id,
            },
            "entry": [
                {
                    "resource": _vital_observation(vital, patient_nic, doctor_id, hospital_id)
                }
                for vital in vitals
            ],
        }

        asyncio.create_task(_send_to_engine(
            data=fhir_msg,
            url="http://127.0.0.1:9000/fhir/send-vitals",
            system_id=hospital_id,
        ))

        return {
            "message": "Vitals sent to engine",
            "fhir_msg": fhir_msg,
        }
    except HTTPException:
        raise
    except Exception as exp:
        logger.error(f"Error sending vitals to engine: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.get("/doctor-visit-notes/{nic}/{doctor_id}", response_model=list[VisitNoteBase])
@limiter.limit("30/minute")
def get_doctors_visit_notes(request: Request, response: Response, nic: str, doctor_id: int, db: Session = Depends(get_db)):
    """
        Retrieve all visit notes of a patient for a specific doctor.

        Input:
        - Path parameters:
            - `nic` (str): Patient NIC identifier.
            - `doctor_id` (int): Doctor identifier.
        - No request body.

        Returns:
        - `200 OK` with list[`VisitNoteBase`].
        - Each item contains:
            - `note_id` (int)
            - `visit_date` (str, formatted datetime)
            - `note_title` (str | null)

        Potential errors:
        - `404 Not Found`: Patient does not exist.
        - `404 Not Found`: Doctor does not exist.
        - `404 Not Found`: No visit notes found for the pair.
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        if db.get(model.Patient, nic) is None:
            logger.warning(f"Patient with NIC {nic} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patient with the given NIC {nic} not found.")
        
        if db.get(model.Doctor, doctor_id) is None:
            logger.warning(f"Doctor with ID {doctor_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Doctor with the given ID {doctor_id} not found.")
        
        visit_notes = db.query(model.VisitingNotes).filter_by(nic=nic, doctor_id=doctor_id).all()
        if not visit_notes:
            logger.warning(f"No visit notes found for NIC {nic} and doctor ID {doctor_id}.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visit notes found for the given NIC {nic} and doctor ID {doctor_id}.")
        return visit_notes
    
    except Exception as exp:
        logger.error(f"Error fetching visit notes for NIC {nic} and doctor ID {doctor_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))
    
@router.get("/visit-note-details/{note_id}", response_model=VisitNoteDetail)
@limiter.limit("30/minute")
def get_visit_note_details(request: Request, response: Response, note_id: str, db: Session = Depends(get_db)):
    """
        Retrieve detailed data for a specific visit note.

        Input:
        - Path parameter:
            - `note_id` (str): Visit note identifier.
        - No request body.

        Returns:
        - `200 OK` with `VisitNoteDetail`:
            - Visit note core fields (`note_id`, `note_title`, `patient_complaint`,
                `diagnosis`, `note_details`, `consultation_bill`, `payment_status`).
            - Optional lab enrichment fields when lab reports exist:
                `lab_name`, `lab_tests`, `test_bill`.

        Potential errors:
        - `404 Not Found`: Visit note does not exist.
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        visit_note = db.get(model.VisitingNotes, note_id)
        if visit_note is None:
            logger.warning(f"Visit note with ID {note_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Visit note with the given ID {note_id} not found.")
        
        response_data = {
            "note_id": visit_note.note_id,
            "note_title": visit_note.note_title,
            "patient_complaint": visit_note.patient_complaint,
            "diagnosis": visit_note.diagnosis,
            "note_details": visit_note.note_details,
            "consultation_bill": visit_note.consultation_bill,
            "payment_status": visit_note.payment_status
        }

        lab_reports = db.query(model.LabReport).filter(model.LabReport.visit_id == visit_note.note_id).all()

        if lab_reports:
            response_data["lab_name"] = lab_reports[0].lab_name
            response_data["lab_tests"] = [lab_report.test_name for lab_report in lab_reports]
            response_data["test_bill"] = sum(lab_report.test_bill for lab_report in lab_reports)

        return response_data
    except Exception as exp:
        logger.error(f"Error fetching visit note details for note ID {note_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))
