from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api import interface_engine
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
async def add_patient(patient: schema.post_patient ,db: Session = Depends(get_db)):
    try:

        if db.query(model.Patient).filter(model.Patient.nic == patient.nic).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"messsage":"nic already exists"})

        new_patient = model.Patient(
            nic = patient.nic,
            name = patient.name,
            phone_no = patient.phone_no,
            gender = patient.gender,
            date_of_birth = patient.date_of_birth,
            address = patient.address
        )
        db.add(new_patient)
        db.flush()


        # call a function for integration engine with params (mpi, name, gender, dob)
        engine_data = {
            "mpi": new_patient.mpi,
            "name": new_patient.name,
            "gender": new_patient.gender,
            "date_of_birth": str(patient.date_of_birth)
        }

        response = await interface_engine.engine_push(engine_data)
        
        if response:
            db.commit()
            db.refresh(new_patient)
            return JSONResponse(content={"message": "data inserted sucessfully", "response": response})
        
        db.rollback()

    except Exception as exp:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")
