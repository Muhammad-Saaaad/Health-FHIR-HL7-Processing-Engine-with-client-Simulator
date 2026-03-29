import time
from threading import Lock

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from schemas import lab_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Visit Note'])

cached_data = {}
rate_limit_store = {}
rate_limit_lock = Lock()


def enforce_rate_limit(
    request: Request,
    response: Response,
    endpoint_key: str,
    limit: int,
    window_seconds: int,
):
    """
    Simple in-memory fixed-window limiter by IP + endpoint.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"{endpoint_key}:{client_ip}"
    now = time.time()

    with rate_limit_lock:
        window_start, count = rate_limit_store.get(key, (now, 0))

        if now - window_start >= window_seconds:
            window_start, count = now, 0

        if count >= limit:
            retry_after = max(1, int(window_seconds - (now - window_start)))
            response.headers["Retry-After"] = str(retry_after)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            )

        count += 1
        rate_limit_store[key] = (window_start, count)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))

@router.get("/lab-reports-by-{note_id}", response_model=list[schema.LabReport], status_code=status.HTTP_200_OK, tags=["Lab"])
def fetch_lab_report(note_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
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
        # 30 requests/minute per client IP for this endpoint.
        enforce_rate_limit(request, response, "lab-reports", limit=30, window_seconds=60)

        notes = db.query(model.LabReport) \
            .filter(model.LabReport.visit_id == note_id).all()
        if not notes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Note id not found or not lab reports for this note")
        return notes

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')

@router.get("/lab_test_search", response_model=list[schema.LoincMaster], status_code=status.HTTP_200_OK, tags=["Lab"])
async def test_search(search_name: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
        * This will get the top 10 case insensetive results that contain the search name in the long common name of the LoincMaster table. 
        * The results are cached in memory for faster retrieval on subsequent searches with the same name.
        * The results are also ordered alphabetically by the long common name of the test.
        * Only the top 10 results are returned to avoid overwhelming the client with too many options.
    """
    try:
        # 20 requests/minute per client IP for this endpoint.
        enforce_rate_limit(request, response, "lab-test-search", limit=20, window_seconds=60)

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')