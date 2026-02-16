from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.patient_schema import GetPatient

router = APIRouter(tags=["patient"])

@router.get("/get_patients", response_model=list[GetPatient], tags=["patient"])
def get_all_patients(db: Session = Depends(get_db)):
    patients = db.query(model.Patient).all()
    return patients

@router.get("/patients/{pid}", response_model=GetPatient, tags=["patient"])
def get_patient_detail(pid: int, db: Session = Depends(get_db)):
    patient = db.get(model.Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient