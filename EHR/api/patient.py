from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas import patient_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Patient'])

@router.get("/patients", response_model=list[schema.get_patient], status_code=status.HTTP_200_OK)
def get_patient(db: Session = Depends(get_db)):
    try:
        all_patients = db.query(model.Patient).all()
        return all_patients
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@router.post("/patients", status_code=status.HTTP_201_CREATED)
def add_patient(patient: schema.post_patient ,db: Session = Depends(get_db)):
    try:

        if db.query(model.Patient).filter(model.Patient.cnic == patient.cnic).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"messsage":"cnic already exists"})

        new_patient = model.Patient(
            doctor_id = patient.doctor_id,
            cnic = patient.cnic,
            name = patient.name,
            phone_no = patient.phone_no,
            gender = patient.gender,
            date_of_birth = patient.date_of_birth,
            address = patient.address
        )
        db.add(new_patient)
        db.commit()
        db.refresh(new_patient)
        return JSONResponse(content={"message": "data inserted sucessfully"})
    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")
