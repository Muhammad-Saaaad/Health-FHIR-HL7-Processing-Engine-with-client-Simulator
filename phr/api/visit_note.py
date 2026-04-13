import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, HTTPException, Depends, Response, Request
from sqlalchemy.orm import Session

from database import get_db
import model
from rate_limiting import limiter
from schemas.visit_note_schema import VisitNoteBase, VisitNoteDetail

router = APIRouter(tags=["Visit Notes"])

logger = logging.getLogger("phr_api_visit_note")
logger.setLevel(logging.INFO)   
handler = RotatingFileHandler(
    r"logs/visit_note.log", 
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=2
)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'))
logger.addHandler(handler)

@router.get("/doctor-visit-notes/{mpi}/{doctor_id}", response_model=list[VisitNoteBase])
@limiter.limit("30/minute")
def get_doctors_visit_notes(request: Request, response: Response, mpi: str, doctor_id: int, db: Session = Depends(get_db)):
    try:
        if db.get(model.Patient, mpi) is None:
            logger.warning(f"Patient with MPI {mpi} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patient with the given MPI {mpi} not found.")
        
        if db.get(model.Doctor, doctor_id) is None:
            logger.warning(f"Doctor with ID {doctor_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Doctor with the given ID {doctor_id} not found.")
        
        visit_notes = db.query(model.VisitingNotes).filter_by(mpi=mpi, doctor_id=doctor_id).all()
        if not visit_notes:
            logger.warning(f"No visit notes found for MPI {mpi} and doctor ID {doctor_id}.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visit notes found for the given MPI {mpi} and doctor ID {doctor_id}.")
        return visit_notes
    
    except Exception as exp:
        logger.error(f"Error fetching visit notes for MPI {mpi} and doctor ID {doctor_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))
    
@router.get("/visit-note-details/{note_id}", response_model=VisitNoteDetail)
@limiter.limit("30/minute")
def get_visit_note_details(request: Request, response: Response, note_id: str, db: Session = Depends(get_db)):
    try:
        visit_note = db.get(model.VisitingNotes, note_id)
        if visit_note is None:
            logger.warning(f"Visit note with ID {note_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Visit note with the given ID {note_id} not found.")
        
        response_data = {
            "note_id": visit_note.note_id,
            "note_title": visit_note.note_title,
            "patient_complaint": visit_note.patient_complaint,
            "diagnosis": visit_note.diagnosis,
            "note_details": visit_note.note_details,
            "consultation_bill": visit_note.consultation_bill,
            "payment_status": visit_note.payment_status
        }

        lab_reports = db.query(model.LabReport).filter(model.LabReport.visit_id == visit_note.note_id).all()

        if lab_reports:
            response_data["lab_name"] = lab_reports[0].lab_name
            response_data["lab_tests"] = [lab_report.test_name for lab_report in lab_reports]
            response_data["test_bill"] = sum(lab_report.test_bill for lab_report in lab_reports)

        return response_data
    except Exception as exp:
        logger.error(f"Error fetching visit note details for note ID {note_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))