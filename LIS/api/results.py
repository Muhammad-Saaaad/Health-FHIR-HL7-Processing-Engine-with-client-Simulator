from datetime import datetime

import model
from database import get_db

from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.result_schema import TestResultOut, MiniTestOut, CompleteTestResultCreate
from schemas.lab_schema import TestRequestOut
from rate_limiting import limiter

router = APIRouter(tags=["Results"])


@router.post("/results/complete", status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def add_complete_result(r_in: CompleteTestResultCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Submit a complete lab result for an accepted and paid test request.

    **Request Body:**
    - `user_id` (int, required): ID of the lab technician submitting the result. Must be a valid user.
    - `test_req_id` (int, required): ID of the test request this result belongs to. Must exist and be accepted.
    - `description` (str, optional): Overall description or summary of the test result.
    - `mini_tests` (list, required): List of individual sub-test results. Each item must include:
        - `test_name` (str): Name of the sub-test (e.g., "Hemoglobin", "WBC Count").
        - `normal_range` (str): Expected normal range (e.g., "13.5–17.5 g/dL").
        - `units` (str): Units of measurement (e.g., "g/dL", "10^3/µL").
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
    - Only one result can be submitted per test request (no duplicate results).

    **Error Responses:**
    - `404 Not Found`: User (Technician) ID not found
    - `404 Not Found`: Test Request not found
    - `404 Not Found`: Test request status is not "Accepted"
    - `400 Bad Request`: A result has already been submitted for this test request

    **Rate Limit:**
    - 15 requests per minute per client IP.
    """
    if not db.get(model.User, r_in.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
        
    req = db.get(model.LabTestRequest, r_in.test_req_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test Request not found.")
    
    if req.status != "Accepted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="test req is not accepted.")
    
    # if db.query(model.LabTestBilling) \
    #     .filter(model.LabTestBilling.test_req_id == r_in.test_req_id).first().payment_status != "Paid":

    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not paid.")

        
    if db.query(model.LabResult).filter(model.LabResult.test_req_id == r_in.test_req_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Result already submitted for this request.")

    result = model.LabResult(
        user_id= r_in.user_id,
        test_req_id = r_in.test_req_id,
        description = r_in.description,
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
                units = mini_test_data.units,
                result_value = mini_test_data.result_value
            )
        )
    db.add_all(db_mini_tests)

    # 4. Update TestRequest status to Completed
    req.status = "Completed"

    db.commit()
    return {"message": "result added"}

@router.get("/results/test_req_id/{test_req_id}", response_model=TestResultOut)
@limiter.limit("10/minute")
def get_test_result(test_req_id: int, request:Request, response: Response, db: Session = Depends(get_db)):
    """
        Retrieve the complete result payload for a test request.

        **Path Parameters:**
        - `test_req_id` (int, required): Lab test request identifier.

        **Response (200 OK):**
        Returns `TestResultOut` with:
        - `result_id`, `user_id`, `test_req_id`, `description`
        - `mini_test_results` (optional list of mini-test entries with
            `mini_test_id`, `test_name`, `normal_range`, `units`, `result_value`).

        **Error Responses:**
        - `404 Not Found`: No result exists for the provided request ID.
    """
    result = db.query(model.LabResult).filter(model.LabResult.test_req_id == test_req_id).first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test result not found for the given test request ID.")
    
    result_out = TestResultOut(
        result_id=result.result_id,
        user_id=result.user_id,
        test_req_id=result.test_req_id,
        description=result.description
    )

    mini_test_results = db.query(model.MiniLabResult).filter(model.MiniLabResult.result_id == result.result_id).all()
    if not mini_test_results:
        return result_out
    
    mini_tests_out = []
    for mini_test in mini_test_results:

        mini_tests_out.append(
            MiniTestOut(
                mini_test_id=mini_test.mini_test_id,
                test_name=mini_test.mini_test_name,
                normal_range=mini_test.normal_range,
                units=mini_test.unit,
                result_value=mini_test.result_value
            )
        )
    result_out.mini_test_results = mini_tests_out
    return result_out



@router.put("/requests/lock_test/{test_req_id}/user_id/{user_id}", response_model=TestRequestOut)
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def lock_test_request(test_req_id: int, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Lock a lab test request to a specific technician to prevent concurrent processing.

    **Path Parameters:**
    - `test_req_id` (int, required): Test request ID to lock.
    - `user_id` (int, required): ID of the technician locking the request.

    **Response (200 OK):**
    Returns the updated test request with `locked_by` set to `user_id`
    and `locked_at` set to the current timestamp.

    **Constraints:**
    - If the request is already locked by a different technician, the lock is rejected.
    - A technician can re-lock their own already-locked request.

    **Error Responses:**
    - `403 Forbidden`: The test request is already locked by a different technician
    - `404 Not Found`: No test requests exist with the given `test_req_id`
    - `404 Not Found`: User (Technician) ID not found

    **Rate Limit:**
    - 15 requests per minute per client IP.
    """
    
    if not db.get(model.User, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
    current_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == test_req_id).first()
    if not current_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test request not found.")
    
    # is the page is locked and it is not locked by you, then error. if it is locked by you, then ok.
    if current_request.locked_by and current_request.locked_by != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This page is already locked by another technician.")
            
    current_request.locked_by = user_id
    current_request.locked_at = datetime.now()

    db.commit()        
    return current_request

@router.put("/requests/unlock_test_request/test_req_id/{test_req_id}/user_id/{user_id}", response_model=TestRequestOut)
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def unlock_test_request(test_req_id: int, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Unlock a lab test request to release it from a technician's hold.

    **Path Parameters:**
        - `test_req_id` (int, required): Test request ID to unlock.
        - `user_id` (int, required): ID of the technician requesting the unlock.

    **Response (200 OK):**
        Returns the updated test request after unlocking.

    **Constraints:**
    - If the request is locked by a different technician, the unlock is rejected.

        **Behavior:**
        - Sets `locked_by = None` and `locked_at = None` for each matched request.

    **Error Responses:**
    - `403 Forbidden`: The test request is locked by a different technician
        - `404 Not Found`: No test requests exist with the given `test_req_id`
    - `404 Not Found`: User (Technician) ID not found.

        **Rate Limit:**
        - 15 requests per minute per client IP.
    """
    if not db.get(model.User, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
    current_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == test_req_id).first()
    if not current_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test request not found.")
    
    if current_request.locked_by != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page is not locked by this user: {user_id}")
            
    current_request.locked_by = None
    current_request.locked_at = None

    db.commit()
    
    return current_request