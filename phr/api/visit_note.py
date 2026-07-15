import logging
from logging.handlers import RotatingFileHandler
import asyncio
from datetime import datetime

from fastapi import APIRouter, status, HTTPException, Depends, Response, Request
from sqlalchemy.orm import Session

from database import get_db
from api.engine_service import send_to_engine
import model
from rate_limiting import limiter
from schemas.visit_note_schema import VisitNoteBase, VisitNoteDetail 
from schemas.vitals_schema import Vitals, SendVitals

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

def _vital_observation(vital: model.Vitals, patient_nic: str, doctor_id: str, hospital_id: str) -> dict:
    observation = {
        "resourceType": "Observation",
        "code": {"text": vital.type},
        "subject": {"reference": f"patient/{patient_nic}"},
        "performer": [{"reference": f"Practitioner/{doctor_id}"}],
        "effectiveDateTime": vital.recorded_at.isoformat(),
        "extension": [
            {
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
        observation["valueQuantity"]= {
            "value": "nan",
            "unit": "nan"
        }
        observation["note"]= [
            {
                "text": "nan"
            }
        ]
    else:
        observation["component"] = [
            {
                "code": {"text": "nan"},
                "valueQuantity": {"value": "nan", "unit": ""},
            },
            {
                "code": {"text": "nan"},
                "valueQuantity": {"value": "nan", "unit": "nan"},
            },
        ]
        observation["valueQuantity"] = {
            "value": vital.value,
            "unit": vital.unit,
        }
        if vital.meal_time:
            observation["note"] = [{"text": vital.meal_time}]
        else:
            observation["note"] = [{"text": ""}]

    return observation

@router.post("/add-vitals", status_code=status.HTTP_201_CREATED)
async def add_vitals(vitals: Vitals, db: Session = Depends(get_db)):
    """
        Store a list of patient vital readings.
    """
    try:
        is_valid_patient = db.query(model.Patient).filter(
            model.Patient.nic == vitals.nic).first()
        
        if not is_valid_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="nic not valid")

        vital =model.Vitals(
                type=vitals.type,
                nic=vitals.nic,
                systolic=vitals.systolic,
                diastolic=vitals.diastolic,
                value=vitals.value,
                unit=vitals.unit,
                meal_time=vitals.meal_time
            )
        db.add(vital)
        db.commit()

        return {
            "message": "Vitals added successfully",
           
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exp:
        db.rollback()
        logger.error(f"Error adding vitals: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.get("/get-all-vitals/", status_code=status.HTTP_200_OK,)
def get_all_vitals(db: Session = Depends(get_db)):
    """
    Retrieve all vitals.
   
    """
    try:
        logger.info("Fetching all vitals")
        vital = db.query(model.Vitals).all()
        logger.info(f"Retrieved {len(vital)} vital from database")
        return vital
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving all vital: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.get("/get-speicific-vitals/{nic}", status_code=status.HTTP_200_OK,)
def get_all_vitals(nic: str, db: Session = Depends(get_db)):
    """
    Retrieve all vitals.
   
    """
    try:
        if not db.query(model.Patient).filter(model.Patient.nic == nic).first():
            logger.warning(f"Patient nic: {nic} not found!")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Not vitals for nic: {nic}!")
        
        vital = db.query(model.Vitals).filter(model.Vitals.nic == nic).all()
        logger.info(f"Retrieved {len(vital)} vital from database")
        return vital
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving all vital: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
    

@router.post("/vitals/send-to-engine", status_code=status.HTTP_200_OK)
async def send_vitals_to_engine(vitals: SendVitals, db: Session = Depends(get_db)):
    """
        Send stored vital readings to the InterfaceEngine as a compact FHIR Bundle.
    """
    try:
        patient_nic = vitals.patient_nic
        doctor_id = vitals.doctor_id

        if not patient_nic or not doctor_id :
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_nic, and doctor_id are required"
            )

        if not db.query(model.Patient).filter(model.Patient.nic == patient_nic).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with nic '{patient_nic}' not found"
            )

        is_doctor = db.query(model.Doctor).filter(model.Doctor.doctor_id == doctor_id).first()
        if not is_doctor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Doctor with id '{doctor_id}' not found"
            )

        vitals = db.query(model.Vitals).filter(model.Vitals.nic == patient_nic).order_by(model.Vitals.recorded_at.desc()).all()
        fhir_msg = {
            "resourceType": "Bundle",
            "type": "message",
            "entry": [
                {
                    "resource": _vital_observation(vital, patient_nic, doctor_id, is_doctor.hospital_id)
                }
                for vital in vitals
            ],
        }

        asyncio.create_task(send_to_engine(data=fhir_msg, url="http://127.0.0.1:9000/fhir/send-vitals", system_id="PHR-1"))

        return {
            "message": "Vitals sent to engine",
            "fhir_msg": fhir_msg
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
