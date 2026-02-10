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
    try:
        all_patients = db.query(model.Patient).all()
        return all_patients
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@router.post("/patients", status_code=status.HTTP_201_CREATED)
async def add_patient(patient: schema.post_patient ,db: Session = Depends(get_db)):
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
    
        fhir_patient =  {
            "resourceType": "Patient",
            "identifier": [
                {
                    "value": new_patient.mpi
                }
            ],
            "name": [
                {
                    "text": new_patient.name
                }
            ],
            "gender": new_patient.gender,
            "birthDate": str(new_patient.date_of_birth)
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
