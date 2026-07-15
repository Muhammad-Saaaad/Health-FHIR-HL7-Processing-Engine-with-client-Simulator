import asyncio
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from fhir_validation import get_fhir_value_by_path, fhir_extract_paths
from database import get_db
import model

router = APIRouter(tags=["Engine"])

logger = logging.getLogger("engine_service_logger")
logger.setLevel(logging.INFO)
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")
if not logger.handlers:
    rotating_file_handler = RotatingFileHandler(
        r"logs\engine_service.log",
        maxBytes=20000, # 20KB
        backupCount=1
    )
    rotating_file_handler.setFormatter(formater)
    logger.addHandler(rotating_file_handler)

async def send_to_engine(data: dict, url: str, system_id: str):
    """
    Send a FHIR data to the InterfaceEngine for routing to downstream services.

    Returns:
        str: The literal value `"sucessfull"` if the engine responds with HTTP 200.

    Raises:
        Exception: If the engine returns a non-200 status (e.g., 502 on partial downstream failure),
                   raises an exception with the engine's error detail so the caller can rollback.
    """
    try:
        logger.info(f"Sending data to engine: {data}")
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            headers = {"Content-Type": "application/json", "System-Id": system_id}
            response = await client.post(url, json=data, headers=headers)
            if response.status_code == 200:
                logger.info(f"Successfully sent data to engine with url {url}")
                return "sucessfull"

            try:
                detail = response.json().get("detail", f"Engine returned {response.status_code}")
            except Exception:
                detail = response.text or f"Engine returned {response.status_code}"
            raise Exception(detail)

    except Exception as exp:
        logger.error(f"Failed to send data to engine: {str(exp)}")
        raise

def _bundle_resources_by_type(json_data: dict) -> dict[str, list[dict]]:
    resources: dict[str, list[dict]] = {}

    if json_data.get("resourceType") != "Bundle":
        resources.setdefault(json_data.get("resourceType"), []).append(json_data)
        return resources

    for entry in json_data.get("entry", []):
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType")
        if resource_type:
            resources.setdefault(resource_type, []).append(resource)

    return resources

def _reference_id(reference: str | None) -> str | None:
    if not reference:
        return None
    return str(reference).split("/")[-1].strip()

def _truncate(value, length: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:length]

def _parse_fhir_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return datetime.now()

def _code_text(code: dict | None) -> str:
    if not isinstance(code, dict):
        return ""
    if code.get("text"):
        return str(code.get("text"))
    coding = code.get("coding", [])
    if isinstance(coding, list) and coding:
        return str(coding[0].get("display") or coding[0].get("code") or "")
    return ""

def _component_value(observation: dict, name: str) -> str | None:
    for component in observation.get("component", []):
        component_name = _code_text(component.get("code", {})).lower()
        if name.lower() in component_name:
            return component.get("valueQuantity", {}).get("value")
    return None

def _component_unit(observation: dict) -> str:
    for component in observation.get("component", []):
        unit = component.get("valueQuantity", {}).get("unit")
        if unit:
            return str(unit)
    return ""

@router.post("/fhir/recieve-vitals", status_code=status.HTTP_201_CREATED)
async def receive_vitals_from_engine(req: Request, db: Session = Depends(get_db)):
    """
    Receive FHIR Observation vitals (single resource or a Bundle with one or more entries) and store them in EHR.

    Each Observation carries:
    - `code.text`: vital type (e.g. "BP", "Temperature", "Sugar") — matched case-insensitively.
    - `subject.reference`: "Patient/{nic}" — resolved to the EHR patient (mpi).
    - `performer[0].reference`: "Practitioner/{id}" — resolved to the EHR doctor (users_id).
    - `extension[0].valueString`: hospital system id (e.g. "EHR-1") used to scope the patient lookup.

    Parsing rules by vital type:
    - BP: systolic/diastolic are read only from the `component` entries, matched by their
      `code.text`; the Observation-level `valueQuantity` is ignored.
    - Sugar: value/unit come from `valueQuantity`, and `note[0].text` holds the
      before/after-meal context.
    - Any other type (e.g. Temperature): value/unit come from `valueQuantity`.

    **Error Responses:**
    - `400 Bad Request`: No usable Observation vitals in the payload, or parsing/database error.
    - `404 Not Found`: Referenced patient or doctor does not exist in the EHR.
    """
    try:
        json_data = await req.json()
        logger.info(f"Received vitals FHIR Data: {json_data}")

        entries = json_data.get("entry", []) if json_data.get("resourceType") == "Bundle" else [{"resource": json_data}]
        vitals = []
        patient_cache = {}
        doctor_cache = {}

        for index, entry in enumerate(entries):
            resource = entry.get("resource", {})
            if resource.get("resourceType") != "Observation":
                continue

            nic = _reference_id(resource.get("subject", {}).get("reference"))
            if not nic:
                logger.warning(f"Skipping Observation at entry index {index}: no patient reference found")
                continue

            performers = resource.get("performer", [])
            doctor_ref = _reference_id(performers[0].get("reference")) if performers else None
            if not doctor_ref:
                logger.warning(f"Skipping Observation at entry index {index}: no practitioner reference found")
                continue

            extensions = resource.get("extension", [])
            hospital_id = extensions[0].get("valueString") if extensions else None

            patient_key = (nic, hospital_id)
            if patient_key not in patient_cache:
                patient_query = db.query(model.Patient).filter(model.Patient.nic == nic)
                if hospital_id:
                    patient_query = patient_query.filter(model.Patient.hospital_id == hospital_id)
                patient_cache[patient_key] = patient_query.first()
            patient = patient_cache[patient_key]
            if patient is None:
                logger.error(f"No patient found for NIC={nic} (hospital_id={hospital_id}) in vitals payload")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No patient found for NIC={nic}")

            if doctor_ref not in doctor_cache:
                doctor_cache[doctor_ref] = db.get(model.Users, int(doctor_ref)) if doctor_ref.isdigit() else None
            doctor = doctor_cache[doctor_ref]
            if doctor is None:
                logger.error(f"No doctor found for reference={doctor_ref} in vitals payload")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No doctor found for reference={doctor_ref}")

            vital_type = _code_text(resource.get("code", {}))
            type_lower = vital_type.strip().lower()

            meal_time = None
            notes = resource.get("note", [])
            if isinstance(notes, list) and notes:
                meal_time = notes[0].get("text")

            if type_lower == "bp":
                systolic = _component_value(resource, "systolic")
                diastolic = _component_value(resource, "diastolic")
                value = None
                unit = _component_unit(resource)
            else:
                # Sugar, temperature, and any other single-value vital; for sugar the
                # note text above carries the before/after-meal context.
                value_quantity = resource.get("valueQuantity", {})
                systolic = None
                diastolic = None
                value = value_quantity.get("value")
                unit = value_quantity.get("unit", "")

            vitals.append(model.Vitals(
                mpi=patient.mpi,
                users_id=doctor.users_id,
                type=str(vital_type),
                systolic=None if systolic is None else str(systolic),
                diastolic=None if diastolic is None else str(diastolic),
                value=None if value is None else str(value),
                unit=str(unit),
                meal_time=None if meal_time is None else str(meal_time),
                recorded_at=_parse_fhir_datetime(resource.get("effectiveDateTime")),
            ))

        if not vitals:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Observation vitals found in FHIR payload")

        db.add_all(vitals)
        db.commit()
        for vital in vitals:
            db.refresh(vital)

        return {
            "message": "Vitals received successfully",
            "count": len(vitals),
            "vital_ids": [vital.vital_id for vital in vitals],
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exp:
        db.rollback()
        logger.error(f"Error processing vitals FHIR data: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.post("/fhir/receive-test-result")
async def receive_test_result_from_engine(req: Request, db: Session = Depends(get_db)):
    """
    Endpoint to receive FHIR DiagnosticReport data from InterfaceEngine, extract test results, and update the corresponding LabTest and TestRequest records in the EHR.

    **Response (200 OK):**
    Returns JSON object:
    - `message` (str): Summary of the update operation for the patient NIC and visit ID.

    **Error Responses:**
    - `400 Bad Request`: Payload parsing, mapping, or database error.
    - `404 Not Found`: No matching TestRequest exists for the provided data.
    """
    try:
        json_data = await req.json()
        system_id = req.headers.get("System-Id", "Unknown-System")

        if db.get(model.Hospital, system_id) is None:
            logger.warning(f"Received test result with unknown system_id: {system_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown system_id: {system_id}")

        logger.info(f"Received FHIR Data: {json_data}")

        patient_nic = ""
        vid = ""
        price = 0.0
        lab_report_data = {}
        mini_lab_results = []
            
        for index, indiviual_entry in enumerate(json_data['entry']):
            resource = indiviual_entry.get("resource", None)
            if not resource:

                logger.warning(f"No resource found in entry index : {index} \n {indiviual_entry}")
                continue

            if resource.get("resourceType") == "ChargeItem":
                print(resource)
                nic = resource.get("subject", "")
                if nic != "":
                    nic = nic.get("reference", "").split("/")
                if len(nic) < 2:
                    logger.warning(f"No patient reference found in entry index : {index} \n {indiviual_entry}")
                    continue
                patient_nic = nic[-1].strip()

                vid = resource.get("context", "")
                if vid != "":
                    vid = vid.get("reference", "").split("/")
                if len(vid) < 2:
                    logger.warning(f"No encounter reference found in entry index : {index} \n {indiviual_entry}")
                    continue
                vid = vid[-1].strip()
                
                priceOverride = resource.get("priceOverride", {})
                price = priceOverride.get("value", 0.0)
            
            elif resource.get("resourceType") == "DiagnosticReport":
                lab_data = resource.get("code", "")
                if lab_data != "":
                    lab_data = lab_data.get("coding", "")
                if isinstance(lab_data, list) and len(lab_data) > 0:
                    lab_report_data['code'] = lab_data[0].get("code", "")
                    lab_report_data['name'] = lab_data[0].get("display", "")

                lab_report_data['description'] = resource.get("code.text", "")
            
            elif resource.get("resourceType") == "Observation":
                mini_result = {}
                mini_result['mini_test_name'] = resource.get("code", "").get("text", "")
                mini_result['result_value'] = resource.get("valueQuantity", "").get("value", "")
                mini_result['unit'] = resource.get("valueQuantity", "").get("unit", "")
                mini_result['normal_range'] = resource.get("referenceRange", "")[0].get("text")
                mini_lab_results.append(mini_result)

        if not patient_nic or not vid:
            print("nic", nic)
            print("nic", vid)
            logger.error(f"Missing patient NIC or visit ID in received FHIR data: {json_data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing patient NIC or visit ID in FHIR data")
        
        is_patient = db.query(model.Patient).filter(model.Patient.nic == patient_nic).first()
        if is_patient is None:
            logger.error(f"No patient found for NIC={patient_nic} in received FHIR data")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No patient found for NIC={patient_nic}")
        
        is_note = db.query(model.VisitingNotes).filter(model.VisitingNotes.note_id == vid).first()
        if is_note is None:
            logger.error(f"No visit note found for MPI={is_patient.mpi}, VID={vid} in received FHIR data")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visit note found for MPI={is_patient.mpi}, VID={vid}")
        
        lab_report = db.query(model.LabReport).filter(model.LabReport.visit_id == vid, model.LabReport.loinc_code == lab_report_data.get("code", "")).first()
        if not lab_report:
            logger.error(f"No lab report found for VID={vid} and LOINC code={lab_report_data.get('code', '')} in received FHIR data")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No lab report found for VID={vid} and LOINC code={lab_report_data.get('code', '')}")
        
        lab_report.description = lab_report_data.get("description", "")
        lab_report.updated_at = datetime.now()
        lab_report.test_status = "Arrived"
        db.add(lab_report)

        all_model_mini_results = []
        for mini_result in mini_lab_results:
            all_model_mini_results.append(model.MiniLabResult(
                report_id=lab_report.report_id,
                test_name=mini_result['mini_test_name'],
                result_value=mini_result['result_value'],
                unit=mini_result['unit'],
                normal_range=mini_result['normal_range']
            ))
        
        db.add_all(all_model_mini_results)

        bill = db.query(model.Bill).filter(model.Bill.bill_id == is_note.bill_id).first()
        bill.lab_charges += float(str(price).strip())
        bill.bill_date = datetime.now()
        db.commit()

        observation_entries = [
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {
                        "text": mini_result.get("mini_test_name", "")
                    },
                    "valueQuantity": {
                        "value": mini_result.get("result_value", ""),
                        "unit": mini_result.get("unit", "")
                    },
                    "referenceRange": [
                        {
                            "text": mini_result.get("normal_range", "")
                        }
                    ]
                }
            }
            for mini_result in mini_lab_results
        ]

        fhir_msg = {
            "resourceType": "Bundle",
            "type": "message",
            "entry": [
                {
                    "resource": {
                        "resourceType": "ChargeItem",
                        "id": "chargeitem-1",
                        "subject": {
                            "reference": "Patient/"+ str(patient_nic)
                        },
                        "context": {
                            "reference":  "Encounter/"+ str(vid)
                        },
                        "priceOverride": {
                            "value": price
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "DiagnosticReport",
                        "code": {
                            "coding": [
                                {
                                    "code": lab_report_data.get("code", ""),
                                    "display": lab_report_data.get("name", "Unknown Test")
                                }
                            ],
                            "text": lab_report_data.get("description", "Unknown description")
                        }
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {
                            "text": "TSH (Thyroid Stimulating Hormone)"
                        },
                        "valueQuantity": {
                            "value": 1.2,
                            "unit": "mIU/L"
                        },
                        "referenceRange": [
                            {
                                "text": "0.4 – 4.2"
                            }
                        ]
                    }
                }
            ]  
        }
        fhir_msg["entry"] = fhir_msg["entry"][:2] + observation_entries

        asyncio.create_task(send_to_engine(data=fhir_msg, url="http://127.0.0.1:9000/receive-test-result", system_id=str(system_id)))
        logger.info(f"Forwarded FHIR test result Bundle to engine for MPI={is_patient.mpi}, VID={vid}")

        return {"message": f"Lab result saved for MPI={is_patient.mpi}, VID={vid}"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) 

@router.post("/fhir/claim-response")
async def take_claim_response_from_engine(req: Request, db: Session = Depends(get_db)):
    """
    Ingest a FHIR ClaimResponse payload from InterfaceEngine and update the matching EHR bill.

    **Response (200 OK):**
    Returns JSON object:
    - `message` (str): Bill status update summary for the patient NIC and visit ID.

    **Error Responses:**
    - `400 Bad Request`: Unknown system ID, payload parsing, mapping, or database error.
    - `404 Not Found`: No matching visit note exists for the claim response.
    """
    try:
        json_data = await req.json()
        system_id = req.headers.get("System-Id", "Unknown-System")
        if db.get(model.Hospital, system_id) is None:
            logger.warning(f"Received claim response with unknown system_id: {system_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown system_id: {system_id}")

        logger.info(f"Recieved FHIR Data: {json_data}")

        # resource_type = json_data['resourceType']
        db_data = {}
        for entry in json_data["entry"]: # this will always recieve resource as bundle.

            resource_type = entry['resource']['resourceType']
            paths = fhir_extract_paths(entry['resource'])
            for path in paths:

                value = get_fhir_value_by_path(json_data, path)
                db_data[path] = value

        nic = str(db_data.get("patient.reference").split("/")[-1]).strip() # NIC
        vid = str(db_data.get("request.reference").split("/")[-1]).strip() # vid
        claim_status = str(db_data.get("status")).strip()
        logger.info(f"Extracted data for DB: NIC={nic}, VID={vid}, Status={claim_status}")

        is_patient = db.query(model.Patient).filter(model.Patient.nic == nic).first()
        if is_patient is None:
            logger.error(f"No patient found for NIC={nic} in claim response")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No patient found for NIC={nic}")

        visit_note = db.query(model.VisitingNotes).filter(model.VisitingNotes.mpi == is_patient.mpi, model.VisitingNotes.note_id == vid).first()
        if visit_note:
            bill = db.get(model.Bill, visit_note.bill_id)
            bill.bill_status = "Paid" if str(claim_status).lower() == "approved" else "Denied"
            bill.bill_date = datetime.now()
            db.add(bill)
            db.commit()
            logger.info(f"Updated bill status to {bill.bill_status} for MPI={is_patient.mpi}, VID={vid}")

            fhir_msg = {
                "resourceType": "ClaimResponse",
                "id": str(uuid4()), 
                "status": bill.bill_status,
                "type": { "coding": [{"code": "professional"}] },
                "use": "claim",
                "patient": {
                    "reference": "patient/"+str(nic) 
                },
                "request": {
                    "reference": "Encounter/"+str(vid)
                },
                "created": bill.bill_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "insurer": {
                    "display": "Jubilee Insurance"
                },
                "outcome": "complete"
            }
            logger.info(f"Prepared FHIR ClaimResponse to send to engine: {fhir_msg}")

            asyncio.create_task(send_to_engine(data=fhir_msg, url="http://127.0.0.1:9000/fhir/send-response-claim", system_id=str(system_id)))
            logger.info(f"Successfully sent claim response to engine for MPI={is_patient.mpi}, VID={vid}")       

            return {"message": f"Bill status updated to {bill.bill_status} for MPI={is_patient.mpi}, VID={vid}"}
        else:
            logger.error(f"No visit note found for MPI={is_patient.mpi}, VID={vid}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visit note found for MPI={is_patient.mpi}, VID={vid}")


    except Exception as e:
        logger.error(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
