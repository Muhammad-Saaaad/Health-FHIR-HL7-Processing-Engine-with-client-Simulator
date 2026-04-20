from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from schemas import lab_schema as schema
from database import get_db
import model
from rate_limiting import limiter

router = APIRouter(tags=['Visit Note'])

cached_data = {}

@router.get("/lab-reports-by-{note_id}", response_model=list[schema.LabReport], status_code=status.HTTP_200_OK, tags=["Lab"])
@limiter.limit("30/minute")
def fetch_lab_report(note_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all lab reports associated with a specific visit note.

    **Path Parameters:**
    - `note_id` (int, required): The unique identifier of the visit note whose lab reports to fetch.

    **Response (200 OK):**
    Returns `list[schema.LabReport]` where each item includes:
    - `report_id` (int)
    - `visit_id` (int)
    - `lab_name` (str)
    - `test_name` (str)
    - `test_status` (str)
    - `created_at` (datetime | null)
    - `updated_at` (datetime | null)

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

@router.get("/lab_test_search", response_model=list[schema.LoincMaster], status_code=status.HTTP_200_OK, tags=["Lab"])
@limiter.limit("80/minute")
async def test_search(search_name: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Search LOINC master tests by partial name.

    **Query Parameters:**
    - `search_name` (str, required): Case-insensitive text to match in `long_common_name`.

    **Response (200 OK):**
    Returns `list[schema.LoincMaster]` (maximum 10 rows), each item containing:
    - `loinc_code` (str)
    - `long_common_name` (str)
    - `short_name` (str | null)
    - `component` (str | null)
    - `system` (str | null)

    **Notes:**
    - Empty `search_name` returns `[]`.
    - Results are cached by search term.
    - Results are sorted by `long_common_name` ascending.
    """
    try:
        if search_name.strip() == "":
            return []

        if search_name in cached_data:
            return cached_data[search_name]
        
        # here ilike is case in-sensetive matching where like is case-sensitive matching
        results = db.query(model.LoincMaster) \
            .filter(model.LoincMaster.long_common_name.ilike(f"%{search_name}%")) \
                .order_by(model.LoincMaster.long_common_name.asc()) \
                    .limit(10).all()
        
        cached_data[search_name] = results
        return results
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')