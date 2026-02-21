from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.orm import Session

from schemas import lab_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Visit Note'])

@router.get("/lab-reports-by-{note_id}", response_model=list[schema.LabReport], status_code=status.HTTP_200_OK, tags=["Lab"])
def fetch_lab_report(note_id: int, db: Session = Depends(get_db)):
    """
    Retrieve all lab reports associated with a specific visit note.

    **Path Parameters:**
    - `note_id` (int, required): The unique identifier of the visit note whose lab reports to fetch.

    **Response (200 OK):**
    Returns a list of lab report objects linked to the visit. Each object includes:
    - Lab report details such as `lab_name`, `test_name`, and any result fields defined in the schema.

    **Constraints:**
    - At least one lab report must be linked to the visit note; otherwise a 404 is returned.

    **Error Responses:**
    - `404 Not Found`: No lab reports exist for the given `note_id`, or the note ID itself does not exist
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        notes = db.query(model.LabReport) \
            .filter(model.LabReport.visit_id == note_id).all()
        if not notes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Note id not found or not lab reports for this note")
        return notes

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')