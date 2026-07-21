from database import get_db
from model import Vitals
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pydantic import BaseModel


class VitalResponse(BaseModel):
    vital_id: int
    mpi: int
    users_id: int
    type: str
    systolic: str | None = None
    diastolic: str | None = None
    value: str | None = None
    unit: str
    meal_time: str | None = None
    recorded_at: datetime

    class Config:
        from_attributes = True  


router = APIRouter(tags=['Vitals'])

# --- API Endpoint ---
@router.get("/patient/vitals", response_model=List[VitalResponse])
def get_patient_vitals(mpi: int, db: Session = Depends(get_db)):
    """
    Kisi specific patient (mpi) k sary vitals fetch krny ki API
    """
    # Database se data query krna
    vitals = db.query(Vitals).filter(Vitals.mpi == mpi).all()
    
    # Agar patient k koi vitals na milain (Optional check)
    if not vitals:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Patient with mpi {mpi} has no recorded vitals."
        )
        
    return vitals