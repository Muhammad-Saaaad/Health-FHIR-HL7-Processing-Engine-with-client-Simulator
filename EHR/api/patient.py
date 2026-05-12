import asyncio
from uuid import uuid4
import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, Response, status, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from api import engine_service
from schemas import patient_schema as schema
from database import get_db
import model
from rate_limiting import limiter

router = APIRouter(tags=['Patient'])

logger = logging.getLogger("patient_service")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/patient_service.log", maxBytes=1000000, backupCount=1)
handler.setFormatter(formatter)
logger.addHandler(handler)


@router.get("/patients/{hospital_id}", response_model=list[schema.get_patient], status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
def get_patient(hospital_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all patients from the EHR system for a specific hospital.
    
    **Path Parameters:**
    - `hospital_id` (int, required): The unique identifier of the hospital to retrieve patients for.

    **Response (200 OK):**
    Returns `list[schema.get_patient]`.

    Each patient object contains:
    - `mpi` (int): Master Patient Index
    - `name` (str): Patient full name
    - `phone_no` (str | null): Patient phone number
    - `gender` (str): Patient gender
    
    **Error Responses:**
    - 409 Conflict: Database or data consistency error
    """
    try:
        all_patients = db.query(model.Patient).filter(model.Patient.hospital_id == hospital_id).all()
        return all_patients
    except Exception as e:
        logger.error(f"Error retrieving patients: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@router.get("/patients/{patient_id}", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
def get_patient(patient_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve a specific patient from the EHR system.

    **Path Parameters:**
    - `patient_id` (int, required): The unique identifier of the patient to retrieve.

    **Response (200 OK):**
    Returns `schema.SpecificPatient` with:
    - `mpi` (int): Master Patient Index
    - `name` (str): Patient full name
    - `phone_no` (str | null): Patient phone number
    - `gender` (str): Patient gender
    - `nic` (str): National identity number
    - `age` (int): Calculated age from `date_of_birth`
    - `address` (str | null): Patient address

    **Error Responses:**
    - 404 Not Found: No patient exists with the given `patient_id`
    - 409 Conflict: Database or data consistency error
    """
    try:
        patient = db.query(model.Patient).filter(model.Patient.mpi == patient_id).first()
        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        
        patient_detail = schema.SpecificPatient(
            mpi=patient.mpi,
            name=patient.name,
            phone_no=patient.phone_no,
            gender=patient.gender,
            nic=patient.nic,
            age=patient.date_of_birth,
            address=patient.address
        )

        return patient_detail
    except Exception as e:
        logger.error(f"Error retrieving patients: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@router.post("/patients", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_patient(patient: schema.post_patient, request: Request, response: Response ,db: Session = Depends(get_db)):
    """
    Register a new patient in the EHR system and sync with FHIR engine.
    
    **Request Body:**
    - `nic` (str, required): National ID/NIC - must be unique, validates against existing records
    - `name` (str, required): Patient's full name
    - `phone_no` (str, optional): Patient's phone number
    - `gender` (str, optional): Patient's gender - will be capitalized automatically
    - `date_of_birth` (date, optional): Patient's DOB in YYYY-MM-DD format
    - `address` (str, optional): Patient's address
    - `policy_number` (str, required): Insurance policy number forwarded to Payer via FHIR Coverage resource
    - `plan_type` (str, required): Insurance plan type forwarded to Payer via FHIR Coverage resource
    
    **Side Effect:** Automatically creates corresponding FHIR Patient + Coverage Bundle in InterfaceEngine,
    which routes the data to downstream systems (LIS, Payer).
    
    **Response (201 Created):**
    Returns JSON object:
    - `message` (str): "data inserted sucessfully"

    **Request Schema (`schema.post_patient`):**
    - `hospital_id` (int)
    - `nic` (str)
    - `name` (str)
    - `phone_no` (str | null)
    - `gender` (str)
    - `date_of_birth` (date)
    - `address` (str | null)
    - `insurance_company` (str)
    - `policy_number` (int)
    - `plan_type` (str)
    
    **Constraints:**
    - NIC must be unique (no duplicates allowed)
    
    **Error Responses:**
    - 400 Bad Request: NIC already exists or FHIR integration failed
    - 422 Unprocessable Entity: Invalid data or missing required fields
    
    **Note:** Registration is rolled back if FHIR registration fails to maintain data consistency
    """
    try:
        hospital = db.get(model.Hospital, patient.hospital_id)
        if hospital is None:
            logger.warning(f"Attempt to register patient with non-existent hospital_id: {patient.hospital_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message":"hospital_id does not exist"})

        # select top 1 from patient where nic = patient.nic
        if db.query(model.Patient).filter(model.Patient.nic == patient.nic).first():
            logger.warning(f"Attempt to register patient with existing NIC: {patient.nic}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message":"nic already exists"})

        new_patient = model.Patient(
            hospital_id = patient.hospital_id,
            nic = patient.nic,
            name = patient.name,
            phone_no = "Not available" if patient.phone_no is None else patient.phone_no,
            gender = patient.gender.capitalize(),
            date_of_birth = patient.date_of_birth,
            address = "Not available" if patient.address is None else patient.address
        )
        db.add(new_patient)
        db.flush()
        db.refresh(new_patient)
        logger.info(f"New patient added in DB: {new_patient.name} (NIC: {new_patient.nic})")

        unique_id = str(uuid4())

        fhir_patient = {
            "resourceType": "Bundle",
            "id": unique_id,
            "type": "message",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": unique_id,
                        "identifier": [
                            { "type": { "coding": [{ "code": "MR" }]}, "value": str(new_patient.mpi)},
                            { "type": { "coding": [{ "code": "NI" }]}, "value": str(patient.nic)}
                        ],
                        "name": [{"text": new_patient.name}],
                        "gender": new_patient.gender,
                        "birthDate": str(new_patient.date_of_birth),
                        "address": [{"text": new_patient.address }],
                        "telecom": [{"value": new_patient.phone_no }]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Coverage",
                        "id": unique_id,
                        "identifier": [{"value": "3"}], # Plan number.
                        "status": "active",
                        "class": [
                            {
                                "type": { "coding": [{"code": "plan"}] },
                                "value": patient.plan_type,
                            }
                        ],
                        "beneficiary": {
                            "reference": str(new_patient.mpi) # patient mpi
                        },
                        "subscriberId": str(patient.policy_number), # policy number
                        "payor": [
                            {
                                "reference": "Organization/insurance-company-001" # insurance company id
                            }
                        ]
                    }
                }
            ]
        }
        logger.info(f"Registering patient in FHIR with data: {fhir_patient}")
        
        config_data= db.query(model.Config).filter(model.Config.sent_to_engine == False) \
            .order_by(desc(model.Config.config_id)).first()
        
        if config_data and config_data.hold_flag: # if we have to hold the data
            history_hospital = config_data.history.get(hospital.name, {})

            if history_hospital:
                history_hospital["add-patient"] = history_hospital.get("add-patient", 0) + 1
            else:
                config_data.history[hospital.name] = history_hospital
                config_data.history[hospital.name]["add-patient"] = 1
            
            endpoint_already_added = False
            for endpoint in config_data.data:
                if endpoint.get("/fhir/add-patient", False): # if endpoint exists in config.
                    endpoint["/fhir/add-patient"].append(fhir_patient)
                    endpoint_already_added = True
                    break
            
            if not endpoint_already_added:
                config_data.data.append({"/fhir/add-patient": [fhir_patient]})

            flag_modified(config_data, "history")
            flag_modified(config_data, "data")
            db.commit()
            logger.info(f"Data added to config for hospital {hospital.name} due to hold flag. Current history: {config_data.history}")
            return {"message": "data added to config due to hold flag"}
        
        asyncio.create_task(engine_service.send_to_engine(fhir_patient, url="http://127.0.0.1:9000/fhir/add-patient"))
        
        db.commit()
        logger.info(f"Patient registered successfully in FHIR: {new_patient.name} (NIC: {new_patient.mpi})")
        return {"message": "data inserted sucessfully"}
    except Exception as exp:
        db.rollback()
        logger.error(f"Exception during patient registration: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")
