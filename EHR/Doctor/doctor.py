from datetime import datetime, timezone

from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import model
from database import get_db
from Doctor import schemas

router = APIRouter(tags=['Doctor'])


@router.get("/patients", response_model=list[schemas.get_patient], status_code=status.HTTP_200_OK)
def get_patient(db: Session = Depends(get_db)):
    try:
        all_patients = db.query(model.Patient).all()
        return all_patients
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
@router.post("/patients", status_code=status.HTTP_201_CREATED)
def add_patient(patient: schemas.post_patient ,db: Session = Depends(get_db)):
    try:
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
    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exp)

@router.post("/visit-note-add", status_code=status.HTTP_201_CREATED)
def add_visit_note(visit_note: schemas.VisitNote ,db: Session = Depends(get_db)):
    try:
        new_bill = model.Bill(
            insurace_amount = visit_note.bill_amount,
            bill_status = False,
        )

        db.add(new_bill)
        db.flush()

        bill_id = new_bill.bill_id

        new_visit_note = model.VisitingNotes(

            patient_id = visit_note.patient_id,
            doctor_id = visit_note.doctor_id,
            bill_id = bill_id,

            note_title = visit_note.note_title,
            patient_complaint = visit_note.patient_complaint,
            dignosis = visit_note.dignosis, 
            note_details = visit_note.note_details
        )
        db.add(new_visit_note)
        db.commit()
        db.refresh(new_visit_note) 
        return JSONResponse(content={"message": "data inserted sucessfully"})
    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")

@router.get("/all-visit-notes{doc_id}/{pid}", response_model=list[schemas.ViewNote] ,status_code=status.HTTP_200_OK)
def visit_note(doc_id: int, pid: int, db: Session = Depends(get_db)):
    try:

        is_patient = db.query(model.Patient).filter(model.Patient.patient_id == pid).first()

        if not is_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient does not exists")
        
        is_doc = db.query(model.Doctor).filter(model.Doctor.doctor_id == doc_id).first()
        if not is_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor does not exists")

        notes = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.doctor_id ==doc_id, model.VisitingNotes.patient_id == pid).all()
        return notes
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')

@router.get("/visit-note{note_id}", response_model=schemas.ViewNote ,status_code=status.HTTP_200_OK)
def visit_note(note_id: int, db: Session = Depends(get_db)):
    try:
        notes = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.note_id == note_id).first()
        if not notes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note id not found")
        return notes
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')
    
@router.get("/lab-reports-by-{note_id}", response_model=list[schemas.LabReport], status_code=status.HTTP_200_OK)
def fetch_lab_report(note_id: int, db: Session = Depends(get_db)):
    try:
        notes = db.query(model.LabReport) \
            .filter(model.LabReport.visit_id == note_id).all()
        if not notes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Note id not found or not lab reports for this note")
        return notes

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')
