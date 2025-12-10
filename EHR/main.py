from datetime import datetime

from fastapi import FastAPI, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import session
import model

from database import engine, get_db
from model import Doctor, Patient, VisitingNotes, Notification, Bill
import schemas

app = FastAPI(title="EHR System", version="1.0.0")
model.base.metadata.create_all(bind=engine)

@app.get("/")
def health_check():
    return {"status": "EHR System is running"}

@app.post("/SignUp", status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: schemas.SignUp, db :session = Depends(get_db)):
    new_doctor = Doctor(
        name = doctor.name,
        email = doctor.email,
        password = doctor.password,
        date_join = doctor.date_join
    )
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    return JSONResponse(content={"data inserted sucessfully"})

@app.get("/patients", response_model=list[schemas.get_patient], status_code=status.HTTP_200_OK)
def get_patient(db: session = Depends(get_db)):
    try:
        all_patients = db.query(Patient).all()
        return all_patients
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@app.post("/patients", response_model=schemas.post_patient, status_code=status.HTTP_200_OK)
def post_patient(patient: schemas.post_patient ,db: session = Depends(get_db)):
    new_patient = Patient(
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
    return JSONResponse(content={"data inserted sucessfully"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)
    # if add reload then you also add the "main:app" else just put app