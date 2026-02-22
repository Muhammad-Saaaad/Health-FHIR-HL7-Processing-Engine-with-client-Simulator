from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api import engine_service
from schemas import patient_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Patient'])

@router.get("/patients", response_model=list[schema.get_patient], status_code=status.HTTP_200_OK)
def get_patient(db: Session = Depends(get_db)):
    """
    Retrieve all patients from the EHR system.
    
    **Query Parameters:** None
    
    **Response:**
    Returns array of all patient records with complete details
    
    **Error Responses:**
    - 409 Conflict: Database or data consistency error
    """
    try:
        all_patients = db.query(model.Patient).all()
        return all_patients
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@router.post("/patients", status_code=status.HTTP_201_CREATED)
async def add_patient(patient: schema.post_patient ,db: Session = Depends(get_db)):
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
    
    **Response:**
    Returns JSON: {"message": "data inserted sucessfully"} if both local and FHIR registration succeed
    
    **Constraints:**
    - NIC must be unique (no duplicates allowed)
    
    **Error Responses:**
    - 400 Bad Request: NIC already exists or FHIR integration failed
    - 422 Unprocessable Entity: Invalid data or missing required fields
    
    **Note:** Registration is rolled back if FHIR registration fails to maintain data consistency
    """
    try:
        # select top 1 from patient where nic = patient.nic
        if db.query(model.Patient).filter(model.Patient.nic == patient.nic).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"messsage":"nic already exists"})

        new_patient = model.Patient(
            nic = patient.nic,
            name = patient.name,
            phone_no = patient.phone_no,
            gender = patient.gender.capitalize(),
            date_of_birth = patient.date_of_birth,
            address = patient.address
        )
        db.add(new_patient)
        db.flush()
        db.refresh(new_patient)
    
        fhir_patient = {
            "resourceType": "Bundle",
            "type": "message",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{"value": new_patient.mpi}],
                        "name": [{"text": new_patient.name}],
                        "gender": new_patient.gender,
                        "birthDate": str(new_patient.date_of_birth),
                        "address": [{"text": new_patient.address}],
                        "telecom": [{"value": new_patient.phone_no}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Coverage",
                        "identifier": [{"value": patient.policy_number}],
                        "type": {"text": patient.plan_type}
                    }
                }
            ]
        }
        response = engine_service.register_engine(fhir_patient)
        
        if response == "sucessfull":
            db.commit()
            # db.rollback()
            return {"message": "data inserted sucessfully"}
        
        db.rollback()
        return JSONResponse({"message": f"Error {response}"}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exp:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")
