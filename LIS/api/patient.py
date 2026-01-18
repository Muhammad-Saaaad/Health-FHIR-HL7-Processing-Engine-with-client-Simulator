from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.patient_schema import Patient

router = APIRouter(tags=["patient"])

# remove this
# @router.post("/reg_patients", response_model=Patient, status_code=status.HTTP_201_CREATED, tags=["patient"])
# def register_patient(patient: Patient, db: Session = Depends(get_db)):

#     if db.query(model.Patient).filter(model.Patient.cnic == patient.cnic).first(): 
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cnic already exists")

#     db_patient = model.Patient(
#         fname = patient.fname,
#         lname = patient.lname,
#         dob = patient.dob,
#         gender = patient.gender
#     )
#     db.add(db_patient)
#     db.commit()
#     db.refresh(db_patient)
#     return db_patient

#################################################################

@router.get("/get_patients", response_model=list[Patient], tags=["patient"])
def get_all_patients(db: Session = Depends(get_db)):
    patients = db.query(model.Patient).all()
    return patients

@router.get("/patients/{pid}", response_model=Patient, tags=["patient"])
def get_patient_detail(pid: int, db: Session = Depends(get_db)):
    patient = db.get(model.Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient