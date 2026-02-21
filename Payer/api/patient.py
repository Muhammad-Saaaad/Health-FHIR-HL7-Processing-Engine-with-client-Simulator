from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import patient_schema as schema

router = APIRouter(tags=["Patients"])

@router.post("/reg_patient", response_model=schema.PatientDisplay, status_code=status.HTTP_201_CREATED, tags=["Patients"])
def register_patient(request: schema.PatientCreate, db: Session = Depends(get_db)):
    """
    Register a new patient in the system.
    
    **Request Body:**
    - `name` (str, required): Patient's full name
    - `cnic` (str, required): CNIC/ID number - must be unique, cannot register duplicate
    - `phone_no` (str, optional): Patient's phone number
    - `gender` (str, optional): Patient's gender (e.g., "Male", "Female")
    - `date_of_birth` (date, optional): Patient's date of birth in YYYY-MM-DD format
    - `user_id` (int, optional): Associated system user ID
    
    **Response:**
    Returns created patient with: p_id (unique ID), name, cnic, date_of_birth, user_id
    
    **Constraints:**
    - CNIC must be unique (cannot register same CNIC twice)
    - user_id must exist in SystemUser table if provided
    
    **Error Responses:**
    - 404 Not Found: Invalid user_id
    - 409 Conflict: Patient with this CNIC already exists
    - 422 Unprocessable Entity: Invalid data format
    """
    is_user = db.query(models.SystemUser).filter(models.SystemUser.user_id == request.user_id).first()

    if not is_user:
        raise HTTPException(status_code=404, detail="Invalid user id")
    
    if db.query(models.Patient).filter(models.Patient.cnic == request.cnic).first():
        raise HTTPException(status_code=409, detail="Patient already exists")


    new_patient = models.Patient(
        name=request.name,
        cnic=request.cnic,
        phone_no=request.phone_no,
        gender=request.gender,
        date_of_birth=request.date_of_birth,
        user_id=request.user_id
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return new_patient

@router.get("/get_all_patients", response_model=list[schema.PatientDisplay], status_code=status.HTTP_200_OK, tags=["Patients"])
def get_all_patients(db: Session = Depends(get_db)):
    """
    Retrieve all patients registered in the system.
    
    **Query Parameters:** None
    
    **Response:**
    Returns array of all patients with: p_id, name, cnic, date_of_birth, user_id
    
    **Note:** Returns empty array if no patients exist
    """
    return db.query(models.Patient).all()

@router.get("/get_patient/{p_id}", response_model=schema.PatientPolicyDetails, status_code=status.HTTP_200_OK, tags=["Patients"])
def get_single_patient(p_id: int, db: Session = Depends(get_db)):
    """
    Retrieve detailed information about a specific patient including their insurance policies.
    
    **Path Parameters:**
    - `p_id` (int, required): Patient ID to retrieve
    
    **Response:**
    Returns patient details with:
    - `p_id`: Patient's unique ID
    - `name`: Patient's name
    - `cnic`: Patient's CNIC/ID number
    - `date_of_birth`: Patient's date of birth
    - `patient_policy`: Array of associated insurance policies with (policy_id, category_name, total_coverage, amount_used, description)
    
    **Error Responses:**
    - 404 Not Found: Patient ID not found
    """
    patient = db.query(models.Patient).filter(models.Patient.p_id == p_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient_policies = []
    for policiy in patient.policies:
        patient_policies.routerend({
            "policy_id": policiy.policy_id,
            "category_name": policiy.category_name,
            "total_coverage": policiy.total_coverage,
            "amount_used" : policiy.amount_used,
            "description": policiy.description
        })
    output = {
        "p_id" : patient.p_id,
        "name" : patient.name,
        "cnic" : patient.cnic,
        "date_of_birth": patient.date_of_birth,

        "patient_policy": patient_policies
    }

    return output
