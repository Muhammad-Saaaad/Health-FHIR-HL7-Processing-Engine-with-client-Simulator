import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from sqlalchemy import case, or_, func
from sqlalchemy.orm import Session

from schemas import lab_schema as schema
from database import get_db
import model
from rate_limiting import limiter

router = APIRouter(tags=['lab'])

logger = logging.getLogger("ehr_lab_service")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/lab.log", maxBytes=1000000, backupCount=2)
handler.setFormatter(formatter)
logger.addHandler(handler)

cached_data = {}


def _dedupe_loinc_records(records: list[model.LoincMaster]) -> list[dict]:
    seen_display_names: set[str] = set()
    deduped_records: list[dict] = []

    for record in records:
        data = record.to_dict()
        display_name = data.get("display_name")

        if display_name in seen_display_names:
            continue

        seen_display_names.add(display_name)
        deduped_records.append(data)

    return deduped_records

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
        logger.info(f"Fetching lab reports for visit note ID: {note_id}")
        notes = db.query(model.LabReport) \
            .filter(model.LabReport.visit_id == note_id).all()
        
        if not notes:
            logger.warning(f"No lab reports found for visit note ID: {note_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Note id not found or not lab reports for this note")
        
        logger.info(f"Retrieved {len(notes)} lab reports for visit note ID: {note_id}")
        return notes

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching lab reports for visit note ID {note_id}: {str(e)}")
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
                - `unit` (str)
                - `result_value` (str)

        Potential errors:
        - `404 Not Found`: Lab report does not exist.
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        logger.info(f"Fetching lab results for report ID: {report_id}")
        lab_report = db.get(model.LabReport, report_id)
        if lab_report is None:
            logger.warning(f"Lab report with ID {report_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lab report with the given ID {report_id} not found.")
        
        response_data = {
            "report_id": lab_report.report_id,
            "test_name": lab_report.test_name,
            "description": lab_report.description,
            "mini_test_results": lab_report.mini_test
        }
        logger.info(f"Successfully retrieved lab results for report ID: {report_id}")
        return response_data
    
    except HTTPException:
        raise
    except Exception as exp:
        logger.error(f"Error fetching lab report details for report ID {report_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


@router.get("/lab_test_preview/{name}", status_code=status.HTTP_200_OK)
def test_loinc(name: str | None = None, db: Session = Depends(get_db)):
    """
    Test endpoint to verify LOINC master data retrieval.

    **Response (200 OK):**
    Returns a list of `LoincMaster` records, each containing:
    - `loinc_code` (str)
    - `long_common_name` (str)
    - `short_name` (str | null)
    - `component` (str | null)
    - `system` (str | null)
    - `display_name` (str | null)
    - `mobile_name` (str | null)

    **Inputs:**
    - `name` can be passed either as a path parameter (`/lab_test_preview/{name}`)
      or query parameter (`/lab_test_preview?name=...`).

    **Notes:**
    - This endpoint is for testing purposes.
    - It loads LOINC records from the table and filters matches in memory.
    - It returns up to 10 matching records.
    - Query parameter form is safer for names containing `/` or other URL-sensitive characters.
    """
    try:
        logger.info(f"LOINC preview search requested for name: {name}")
        normalized_name = " ".join((name or "").split())
        if normalized_name == "":
            logger.debug("Empty search term provided, returning empty list")
            return []

        needle = normalized_name.lower()
        all_records = db.query(model.LoincMaster).all()
        logger.debug(f"Total LOINC records in database: {len(all_records)}")

        filtered = []
        for record in all_records:
            long_common_name = (record.long_common_name or "").lower()
            short_name = (record.short_name or "").lower()
            component = (record.component or "").lower()
            loinc_code = (record.loinc_code or "").lower()

            if (
                needle in long_common_name
                or needle in short_name
                or needle in component
                or needle in loinc_code
            ):
                filtered.append(record)

        results = [r.to_dict() for r in filtered[:10]]
        logger.info(f"LOINC preview search for '{normalized_name}' returned {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"Error in LOINC preview search for name '{name}': {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')

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
        logger.info(f"LOINC search requested for: '{search_name}'")
        # Normalize extra whitespace so equivalent inputs map to one cache key.
        normalized_search = " ".join(search_name.split())
        cache_key = normalized_search.lower()

        if normalized_search == "":
            logger.debug("Empty search term provided, returning empty list")
            return []

        if cache_key in cached_data:
            logger.debug(f"Returning cached results for search term: '{normalized_search}'")
            return cached_data[cache_key]

        pattern      = f"%{normalized_search}%"
        starts_with  = f"{normalized_search}%"
        word_match   = f"% {normalized_search} %"

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
                .order_by(relevance, func.length(model.LoincMaster.long_common_name)) \
                    .limit(25).all()
        data = _dedupe_loinc_records(results)

        # Avoid caching empty result sets; they can become stale after data updates.
        if data:
            logger.debug(f"Caching {len(data)} results for search term: '{normalized_search}'")
            cached_data[cache_key] = data

        logger.info(f"LOINC search for '{normalized_search}' returned {len(data)} results")
        return data
    except Exception as e:
        logger.error(f"Error in LOINC search for term '{search_name}': {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')