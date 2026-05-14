from datetime import datetime

from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.lab_schema import TestRequestOut, TestRequestStatusUpdate
from rate_limiting import limiter

router = APIRouter(tags=["Test Requests"])

# @router.post("/test_requests", response_model=TestRequestOut, status_code=status.HTTP_201_CREATED, tags=["Test Requests"])
# @limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
# def create_test_request(data: TestRequestCreate, request: Request, response: Response, db: Session = Depends(get_db)):
#     """
#     Create a new lab test request for a patient.

#     **Request Body:**
#     - `nic` (str, required): The NIC/CNIC of the patient requesting the test.
#       Must match an existing patient record.
#     - `test_name` (str, required): Name of the lab test to be performed (e.g., "CBC", "Blood Sugar").

#     **Response (201 Created):**
#     Returns the created test request object including:
#     - `test_req_id`: Auto-generated unique test request ID
#     - `nic`: Patient NIC/CNIC
#     - `test_name`: The requested test name
#     - `status`: Defaults to "Pending" on creation
#     - `locked_by`: None (not locked initially)
#     - `locked_at`: None (not locked initially)

#     **Note:**
#     - The patient is looked up by NIC/CNIC.

#     **Error Responses:**
#     - `404 Not Found`: No patient found matching the given `nic`
#     """
#     is_patient = db.query(model.Patient).filter(model.Patient.nic == data.nic).first()
    
#     if not is_patient:
#         raise HTTPException(status_code=404, detail="Patient not found")
        
#     db_request = model.LabTestRequest(
#         nic = is_patient.nic,
#         test_name = data.test_name,
#         status = "Pending",
#         locked_by = None,
#         locked_at = None
#     )
#     db.add(db_request)
#     db.commit()
#     db.refresh(db_request)
#     return db_request

@router.get("/requests/accepted/payment/paid", response_model=list[TestRequestOut], tags=["Test Requests"])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_accepted_requests(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all lab test requests that have been accepted AND whose payment has been marked as "Paid".

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of test request objects filtered to `status == "Accepted"` and joined with
    billing records where `payment_status == "Paid"`.

    Response type: `list[TestRequestOut]`, each item contains:
    - `test_req_id` (int)
    - `nic` (str)
    - `test_name` (str)
    - `status` (str)
    - `locked_by` (int | null)
    - `locked_at` (datetime | null)

    **Rate Limit:**
    - 20 requests per minute per client IP.

    **Note:**
    - A test request must satisfy both conditions: accepted status AND paid billing.
    - These are the requests that are ready to be processed by a lab technician.
    - Returns an empty list if no such records exist.
    """
    accepted_requests = db.query(model.LabTestRequest).join(model.LabTestBilling) \
        .filter(model.LabTestRequest.status == "Accepted", model.LabTestBilling.payment_status == "Paid").all()

    return accepted_requests

@router.put("/requests/update_report_status", response_model=list[TestRequestOut], tags=["Test Requests"])
@limiter.limit("15/minute")  # Limit to 10 requests per minute per IP
def update_request_status(status_update: TestRequestStatusUpdate, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Bulk update test-request statuses for a visit and create billing rows.

    **Path Parameters:** None

    **Request Body (`TestRequestStatusUpdate`):**
    - `req_id_status` (dict[int, str], required): Mapping of test request IDs to target statuses.
      Example: `{123: "Accepted", 124: "Declined"}`.
    - `req_id_bill` (dict[int, float], required): Mapping of test request IDs to billing amounts.
      Example: `{123: 1200.0, 124: 900.0}`.
    - `user_id` (int, required): Technician ID that must match each request lock owner.
    - `visit_id` (str, required): Visit ID that all request IDs in the payload must belong to.

    **Behavior:**
    - Verifies at least one test request exists for `visit_id`.
    - For each request in `req_id_status`:
        - Validates status is one of `Pending`, `Accepted`, `Declined`, `Completed`.
        - Validates request ID exists.
        - Validates request `vid` matches payload `visit_id`.
        - Validates request is locked and locked by `user_id`.
        - Validates the same request ID exists in `req_id_bill`.
    - Updates each request status.
    - Creates one `LabTestBilling` row per updated request with:
        - `nic`, `test_req_id`, `vid` from the request
        - `bill_amount` from `req_id_bill[req_id]`
        - `payment_status` set to `"pending"`

    **Response (200 OK):**
    Returns `list[TestRequestOut]`, where each item contains:
    - `test_req_id` (int)
    - `nic` (str)
    - `test_name` (str)
    - `status` (str)
    - `locked_by` (int | null)
    - `locked_at` (datetime | null)

    **Error Responses:**
    - `400 Bad Request`: Invalid status value.
    - `400 Bad Request`: Request visit ID does not match payload `visit_id`.
    - `403 Forbidden`: Request is not locked or is locked by another technician.
    - `404 Not Found`: Visit ID not found.
    - `404 Not Found`: Test request ID not found.
    - `404 Not Found`: Request ID present in `req_id_status` but missing from `req_id_bill`.
    - `429 Too Many Requests`: Rate limit exceeded (`15/minute`).
    - `500 Internal Server Error`: Unexpected unhandled server/database error.
    """
    if not db.query(model.LabTestRequest).filter(model.LabTestRequest.vid == status_update.visit_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Visit ID {status_update.visit_id} not found.")
    
    updated_requests = []
    add_req_bill = []
    for req_id, new_status in status_update.req_id_status.items():

        if new_status not in ("Pending", "Accepted", "Declined", "Completed"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status value: {new_status}. Must be one of: Pending, Accepted, Declined.")
        
        updated_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == req_id).first()
        if not updated_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Test Request with ID {req_id} not found.")
        
        if updated_request.vid != status_update.visit_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"The visit id {updated_request.vid} of lab request {req_id} does not match the provided visit ID {status_update.visit_id}.")
        
        if not updated_request.locked_by:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Cannot update status as the request {req_id} is not locked by any technician.")
        
        if updated_request.locked_by != status_update.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Cannot update status as the request {req_id} is locked by another technician.")
        
        if req_id not in status_update.req_id_bill:
            raise HTTPException(status=status.HTTP_404_NOT_FOUND, detail=f"Their was a conflit in the req_id_status {status_update.req_id_status} and req_id_bill {status_update.req_id_bill}. The req_id {req_id} is not found in the req_id_bill.")
        
        if status_update.req_id_bill[req_id] < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid bill amount for request ID {req_id}. Bill amount cannot be negative.")
        
        updated_request.status = new_status
        updated_requests.append(updated_request)

        req_bill = model.LabTestBilling(
            nic=updated_request.nic,
            test_req_id=updated_request.test_req_id,
            bill_amount=status_update.req_id_bill[req_id],
            payment_status="pending",
            vid= updated_request.vid
        )
        add_req_bill.append(req_bill)

    db.add_all(add_req_bill)
    db.commit()
    db.refresh(updated_request)
    return  updated_requests

@router.put("/requests/lock_test_request/visit_id/{visit_id}/user_id/{user_id}", response_model=list[TestRequestOut], tags=["Test Requests"])
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def lock_test_request(visit_id: str, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Lock a lab test request to a specific technician to prevent concurrent processing.

    **Path Parameters:**
    - `visit_id` (str, required): Visit ID whose related test requests should be locked.
    - `user_id` (int, required): ID of the technician locking the requests.

    **Response (200 OK):**
    Returns `list[TestRequestOut]` with `locked_by` set to `user_id`
    and `locked_at` set to the current timestamp.

    **Constraints:**
    - If the request is already locked by a different technician, the lock is rejected.
    - A technician can re-lock their own already-locked request.

    **Error Responses:**
    - `403 Forbidden`: The test request is already locked by a different technician
    - `404 Not Found`: No test requests exist with the given `visit_id`
    - `404 Not Found`: User (Technician) ID not found

    **Rate Limit:**
    - 15 requests per minute per client IP.
    """
    
    if not db.get(model.User, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
    current_requests = db.query(model.LabTestRequest).filter(model.LabTestRequest.vid == visit_id).all()
    if not current_requests:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit Id not found")
    
    for current_request in current_requests:

        # is the page is locked and it is not locked by you, then error. if it is locked by you, then ok.
        if current_request.locked_by and current_request.locked_by != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This page is already locked by another technician.")
            
        current_request.locked_by = user_id
        current_request.locked_at = datetime.now()

    db.commit()        
    return current_requests

@router.put("/requests/unlock_test_request/visit_id/{visit_id}/user_id/{user_id}", response_model=list[TestRequestOut], tags=["Test Requests"])
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def unlock_test_request(visit_id: str, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Unlock a lab test request to release it from a technician's hold.

    **Path Parameters:**
        - `visit_id` (str, required): Visit ID whose related test requests should be unlocked.
        - `user_id` (int, required): ID of the technician requesting the unlock.

    **Response (200 OK):**
        Returns `list[TestRequestOut]` after unlocking (`locked_by = null`, `locked_at = null`).

    **Constraints:**
    - If the request is locked by a different technician, the unlock is rejected.

    **Behavior:**
    - Sets `locked_by = None` and `locked_at = None` for each matched request.

    **Error Responses:**
    - `403 Forbidden`: The test request is locked by a different technician
    - `404 Not Found`: No test requests exist with the given `visit_id`
    - `404 Not Found`: User (Technician) ID not found.

    **Rate Limit:**
    - 15 requests per minute per client IP.
    """
    if not db.get(model.User, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
    current_requests = db.query(model.LabTestRequest).filter(model.LabTestRequest.vid == visit_id).all()
    if not current_requests:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit Id not found")
    
    for current_request in current_requests:

        # if not current_request.locked_by: # if page is not locked, then you cannot unlock this page.
        #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page is not locked")
        
        if current_request.locked_by != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page is not locked by this user: {user_id}")
            
        current_request.locked_by = None
        current_request.locked_at = None

    db.commit()
    
    return current_requests
