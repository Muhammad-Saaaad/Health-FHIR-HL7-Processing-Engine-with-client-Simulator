from datetime import datetime

from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.lab_schema import (
    TestRequestCreate, 
    TestRequestOut,
    TestRequestStatusUpdate,
    CompleteTestResultCreate
)

router = APIRouter(tags=["Test Requests"])

@router.post("/test_requests", response_model=TestRequestOut, status_code=status.HTTP_201_CREATED, tags=["Test Requests"])
def create_test_request(request: TestRequestCreate, db: Session = Depends(get_db)):
    """
    Create a new lab test request for a patient.

    **Request Body:**
    - `patient_cnic` (str, required): The CNIC (National ID) of the patient requesting the test.
      Must match an existing patient record.
    - `test_name` (str, required): Name of the lab test to be performed (e.g., "CBC", "Blood Sugar").

    **Response (201 Created):**
    Returns the created test request object including:
    - `test_req_id`: Auto-generated unique test request ID
    - `patient_id`: Internal patient ID resolved from CNIC
    - `test_name`: The requested test name
    - `status`: Defaults to "Pending" on creation
    - `locked_by`: None (not locked initially)
    - `locked_at`: None (not locked initially)

    **Note:**
    - The patient is looked up by CNIC. The first patient whose CNIC does NOT match is used
      (this may be a bug in the current implementation; the filter uses `!=` instead of `==`).

    **Error Responses:**
    - `404 Not Found`: No patient found matching the given `patient_cnic`
    """
    is_patient = db.query(model.Patient).filter(model.Patient.cnic != request.patient_cnic).first()
    
    if not is_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    db_request = model.LabTestRequest(
        patient_id = is_patient.pid,
        test_name = request.test_name,
        status = "Pending",
        decline_reason = None,
        locked_by = None,
        locked_at = None
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request

@router.get("/requests/pending", response_model=list[TestRequestOut], tags=["Test Requests"])
def get_pending_requests(db: Session = Depends(get_db)):
    """
    Retrieve all lab test requests that are currently in "Pending" status.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of test request objects with `status == "Pending"`. Each object includes:
    - `test_req_id`, `patient_id`, `test_name`, `status`, `decline_reason`, `locked_by`, `locked_at`

    **Note:**
    - Returns an empty list if there are no pending test requests.
    """
    return db.query(model.LabTestRequest).filter(model.LabTestRequest.status == "Pending").all()

@router.get("/requests/accepted/payment/paid", response_model=list[TestRequestOut], tags=["Test Requests"])
def get_accepted_requests(db: Session = Depends(get_db)):
    """
    Retrieve all lab test requests that have been accepted AND whose payment has been marked as "Paid".

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of test request objects filtered to `status == "Accepted"` and joined with
    billing records where `payment_status == "Paid"`. Each object includes full test request details.

    **Note:**
    - A test request must satisfy both conditions: accepted status AND paid billing.
    - These are the requests that are ready to be processed by a lab technician.
    - Returns an empty list if no such records exist.
    """
    accepted_requests = db.query(model.LabTestRequest).join(model.LabTestBilling) \
        .filter(model.LabTestRequest.status == "Accepted", model.LabTestBilling.payment_status == "Paid").all()

    return accepted_requests

@router.put("/requests/{req_id}/status", response_model=TestRequestOut, tags=["Test Requests"])
def update_request_status(req_id: int, status_update: TestRequestStatusUpdate, db: Session = Depends(get_db)):
    """
    Update the status of a lab test request (e.g., accept or decline it).

    **Path Parameters:**
    - `req_id` (int, required): The unique ID of the test request to update.

    **Request Body:**
    - `status` (str, required): New status to assign (e.g., "Accepted", "Declined").
    - `decline_reason` (str, optional): Reason for declining the request. Should be provided if status is "Declined".

    **Response (200 OK):**
    Returns the updated test request object with the new `status` and `decline_reason`.

    **Error Responses:**
    - `404 Not Found`: No test request exists with the given `req_id`
    """
    updated_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == req_id).first()
    
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
    
    updated_request.status = status_update.status
    updated_request.decline_reason = status_update.decline_reason

    db.commit()
    db.refresh(updated_request)
    return updated_request

@router.put("/requests/{req_id}/lock", response_model=TestRequestOut, tags=["Test Requests"])
def lock_test_request(req_id: int, user_id: int, db: Session = Depends(get_db)):
    """
    Lock a lab test request to a specific technician to prevent concurrent processing.

    **Path Parameters:**
    - `req_id` (int, required): The unique ID of the test request to lock.

    **Query Parameters:**
    - `user_id` (int, required): ID of the technician locking the request.

    **Response (200 OK):**
    Returns the updated test request with `locked_by` set to `user_id` and `locked_at` set to the current timestamp.

    **Constraints:**
    - If the request is already locked by a different technician, the lock is rejected.
    - A technician can re-lock their own already-locked request.

    **Error Responses:**
    - `403 Forbidden`: The test request is already locked by a different technician
    - `404 Not Found`: No test request exists with the given `req_id`
    """
    current_request = db.get(model.LabTestRequest, req_id)
    if current_request and current_request.locked_by and current_request.locked_by != user_id:
        raise HTTPException(status_code=403, detail="Test is already locked by another technician.")
        
    current_request.locked_by = user_id
    current_request.locked_at = datetime.now()

    db.commit()
    db.refresh(current_request)
    
    updated_request = db.get(model.LabTestRequest, req_id)
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
        
    return updated_request

@router.put("/requests/{req_id}/unlock", response_model=TestRequestOut, tags=["Test Requests"])
def unlock_test_request(req_id: int, user_id: int, db: Session = Depends(get_db)):
    """
    Unlock a lab test request to release it from a technician's hold.

    **Path Parameters:**
    - `req_id` (int, required): The unique ID of the test request to unlock.

    **Query Parameters:**
    - `user_id` (int, required): ID of the technician requesting the unlock.

    **Response (200 OK):**
    Returns the updated test request object after the unlock operation.

    **Constraints:**
    - If the request is locked by a different technician, the unlock is rejected.

    **Note:**
    - This endpoint currently sets `locked_by` to `user_id` rather than clearing it to `None`.
      This may be a bug — the intended behavior is likely to clear the lock.

    **Error Responses:**
    - `403 Forbidden`: The test request is locked by a different technician
    - `404 Not Found`: No test request exists with the given `req_id`
    """
    current_request = db.get(model.LabTestRequest, req_id)
    if current_request and current_request.locked_by and current_request.locked_by != user_id:
        raise HTTPException(status_code=403, detail="Test is already locked by another technician.")
        
    test_req = db.query(model.LabTestRequest).where(model.LabTestRequest.test_req_id == req_id).first()
    test_req.locked_by = user_id
    test_req.locked_at = datetime.now()

    db.commit()
    db.refresh(test_req)
    
    updated_request = db.get(model.LabTestRequest, req_id)
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
        
    return updated_request


@router.post("/results/complete", status_code=status.HTTP_201_CREATED, tags=["Results"])
def add_complete_result(r_in: CompleteTestResultCreate, db: Session = Depends(get_db)):
    """
    Submit a complete lab result for an accepted and paid test request.

    **Request Body:**
    - `user_id` (int, required): ID of the lab technician submitting the result. Must be a valid user.
    - `test_req_id` (int, required): ID of the test request this result belongs to. Must exist and be accepted.
    - `description` (str, optional): Overall description or summary of the test result.
    - `mini_tests` (list, required): List of individual sub-test results. Each item must include:
        - `test_name` (str): Name of the sub-test (e.g., "Hemoglobin", "WBC Count").
        - `normal_range` (str): Expected normal range (e.g., "13.5–17.5 g/dL").
        - `result_value` (str): The actual measured value for this patient.

    **Response (201 Created):**
    Returns a confirmation message:
    - `message`: "result added"

    **Side Effects:**
    - Automatically updates the test request `status` to "Completed".
    - Creates individual `MiniLabResult` records for each item in `mini_tests`.

    **Constraints:**
    - `user_id` must refer to a valid technician in the User table.
    - `test_req_id` must refer to an existing test request with `status == "Accepted"`.
    - The associated billing record must have `payment_status == "Paid"`.
    - Only one result can be submitted per test request (no duplicate results).

    **Error Responses:**
    - `404 Not Found`: User (Technician) ID not found
    - `404 Not Found`: Test Request not found
    - `404 Not Found`: Test request status is not "Accepted"
    - `404 Not Found`: Payment has not been made for this test request
    - `400 Bad Request`: A result has already been submitted for this test request
    """
    if not db.get(model.User, r_in.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
        
    req = db.get(model.LabTestRequest, r_in.test_req_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test Request not found.")
    
    if req.status != "Accepted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="test req is not accepted.")
    
    if db.query(model.LabTestBilling) \
        .filter(model.LabTestBilling.test_req_id == r_in.test_req_id).first().payment_status != "Paid":

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not paid.")

        
    if db.query(model.LabResult).filter(model.LabResult.test_req_id == r_in.test_req_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Result already submitted for this request.")

    result = model.LabResult(
        user_id= r_in.user_id,
        test_req_id = r_in.test_req_id,
        description = r_in.description,
        created_at=datetime.now()
    )
    db.add(result)
    db.flush()

    db_mini_tests = []
    for mini_test_data in r_in.mini_tests:
        db_mini_tests.append(
            model.MiniLabResult(
                result_id=result.result_id,
                test_name = mini_test_data.test_name,
                normal_range = mini_test_data.normal_range,
                result_value = mini_test_data.result_value
            )
        )
    db.add_all(db_mini_tests)

    # 4. Update TestRequest status to Completed
    req.status = "Completed"
    db.add(req) 

    db.commit()
    return {"message": "result added"}