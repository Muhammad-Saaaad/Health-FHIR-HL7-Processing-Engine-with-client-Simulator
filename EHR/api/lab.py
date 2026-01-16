from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.orm import Session

from schemas import lab_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Visit Note'])

@router.get("/lab-reports-by-{note_id}", response_model=list[schema.LabReport], status_code=status.HTTP_200_OK, tags=["Lab"])
def fetch_lab_report(note_id: int, db: Session = Depends(get_db)):
    try:
        notes = db.query(model.LabReport) \
            .filter(model.LabReport.visit_id == note_id).all()
        if not notes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Note id not found or not lab reports for this note")
        return notes

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')