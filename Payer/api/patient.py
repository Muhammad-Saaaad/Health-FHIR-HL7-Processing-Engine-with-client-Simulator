from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import patient_schema as schema

router = APIRouter(tags=["Patients"])

@router.post("/reg_patient", response_model=schema.PatientDisplay, status_code=status.HTTP_201_CREATED, tags=["Patients"])
def register_patient(request: schema.PatientCreate, db: Session = Depends(get_db)):

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
    return db.query(models.Patient).all()

@router.get("/get_patient/{p_id}", response_model=schema.PatientPolicyDetails, status_code=status.HTTP_200_OK, tags=["Patients"])
def get_single_patient(p_id: int, db: Session = Depends(get_db)):
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
