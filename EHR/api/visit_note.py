from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas import visit_note_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Visit Note'])

@router.post("/visit-note-add", status_code=status.HTTP_201_CREATED)
def add_visit_note(visit_note: schema.VisitNote ,db: Session = Depends(get_db)):
    try:
        new_bill = model.Bill(
            insurance_amount = visit_note.bill_amount,
            bill_status = False,
        )

        db.add(new_bill)
        db.flush()

        bill_id = new_bill.bill_id
        if not db.get(model.Bill, bill_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bill not added due to internal issues")

        new_visit_note = model.VisitingNotes(
            mpi = visit_note.mpi,
            doctor_id = visit_note.doctor_id,
            bill_id = bill_id,

            note_title = visit_note.note_title,
            patient_complaint = visit_note.patient_complaint,
            dignosis = visit_note.dignosis, 
            note_details = visit_note.note_details
        )
        db.add(new_visit_note)
        db.flush()

        if visit_note.test_names:
            
            lab_models = []
            for test in visit_note.test_names:
                lab_models.append(
                    model.LabReport(
                        visit_id = new_visit_note.note_id,
                        lab_name = visit_note.lab_name,
                        test_name = test
                    )
                )
            db.add_all(lab_models)

        db.commit()
        db.refresh(new_visit_note)
        return JSONResponse(content={"message": "data inserted sucessfully"})
        
    except Exception as exp:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")


@router.get("/all-visit-notes{doc_id}/{pid}", response_model=list[schema.ViewNote] ,status_code=status.HTTP_200_OK)
def visit_note(doc_id: int, pid: int, db: Session = Depends(get_db)):
    try:

        is_patient = db.query(model.Patient).filter(model.Patient.mpi == pid).first()

        if not is_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient does not exists")
        
        is_doc = db.query(model.Doctor).filter(model.Doctor.doctor_id == doc_id).first()
        if not is_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor does not exists")

        notes = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.doctor_id ==doc_id, model.VisitingNotes.mpi == pid).all()
        return notes
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')

@router.get("/visit-note{note_id}", response_model=schema.ViewNote ,status_code=status.HTTP_200_OK)
def visit_note(note_id: int, db: Session = Depends(get_db)):
    try:
        notes = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.note_id == note_id).first()
        if not notes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note id not found")
        return notes
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')
    