from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from sqlalchemy import case, or_, func
from sqlalchemy.orm import Session

from schemas import lab_schema as schema
from database import get_db
import model
from rate_limiting import limiter

router = APIRouter(tags=['lab'])

cached_data = {}

@router.get("/lab-reports-by-{note_id}", response_model=list[schema.LabReport], status_code=status.HTTP_200_OK)
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

@router.get("/lab-results/{report_id}", response_model=schema.LabResult)
@limiter.limit("30/minute")
def get_lab_results(report_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
        Retrieve detailed result data for a single lab report.

        Input:
        - Path parameter:
            - `report_id` (int): Lab report identifier.
        - No request body.

        Returns:
        - `200 OK` with `LabResult` payload:
            - `report_id` (int)
            - `test_name` (str)
            - `description` (str | null)
            - `mini_test_results` (list[`LabMiniTestResult`] | null), where each mini test has:
                - `mini_test_id` (int)
                - `test_name` (str)
                - `normal_range` (str)
                - `result_value` (str)

        Potential errors:
        - `404 Not Found`: Lab report does not exist.
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        lab_report = db.get(model.LabReport, report_id)
        if lab_report is None:
            # logger.warning(f"Lab report with ID {report_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lab report with the given ID {report_id} not found.")
        
        response_data = {
            "report_id": lab_report.report_id,
            "test_name": lab_report.test_name,
            "description": lab_report.description,
            "mini_test_results": lab_report.mini_test
        }
        return response_data
    
    except Exception as exp:
        # logger.error(f"Error fetching lab report details for report ID {report_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.get("/lab_test_search", response_model=list[schema.LoincMaster], status_code=status.HTTP_200_OK)
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
    - `display_name` (str | null)
    - `mobile_name` (str | null)

    **Notes:**
    - Empty `search_name` returns `[]`.
    - Results are cached by search term.
    - Results are sorted by `long_common_name` ascending.
    """
    try:
        if search_name.strip() == "":
            return []

        if search_name.lower().strip() in cached_data:
            return cached_data[search_name.lower().strip()]

        pattern      = f"%{search_name}%"
        starts_with  = f"{search_name}%"
        word_match   = f"% {search_name} %"

        relevance = case(
            (model.LoincMaster.long_common_name.ilike(pattern),        1),  # exact
            (model.LoincMaster.long_common_name.ilike(starts_with),  2),  # starts with
            (model.LoincMaster.component.ilike(starts_with),         3),  # component starts
            (model.LoincMaster.long_common_name.ilike(word_match),   4),  # whole word
            else_=5
        )
        
        # here ilike is case in-sensetive matching where like is case-sensitive matching
        results = db.query(model.LoincMaster) \
            .filter(
                or_(
                    model.LoincMaster.long_common_name.ilike(pattern),
                    model.LoincMaster.short_name.ilike(pattern),
                    model.LoincMaster.component.ilike(pattern),
                    model.LoincMaster.loinc_code.ilike(pattern),
                )) \
                .order_by(relevance, func.len(model.LoincMaster.long_common_name)) \
                    .limit(15).all()
        data = [r.to_dict() for r in results]
        cached_data[search_name.lower().strip()] = data
        return data
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')