from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import session

import model
from database import get_db
import schemas

router = APIRouter(tags=['Doctor'])


@router.get("/patients", response_model=list[schemas.get_patient], status_code=status.HTTP_200_OK)
def get_patient(db: session = Depends(get_db)):
    try:
        all_patients = db.query(model.Patient).all()
        return all_patients
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@router.post("/patients", response_model=schemas.post_patient, status_code=status.HTTP_200_OK)
def post_patient(patient: schemas.post_patient ,db: session = Depends(get_db)):
    new_patient = model.Patient(
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

