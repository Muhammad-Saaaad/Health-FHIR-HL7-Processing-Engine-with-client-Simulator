from datetime import datetime

from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.lab_schema import TestRequestOut, TestRequestStatusUpdate, LabTestBase, LabTestCreate, LabResultOut
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

@router.get("/requests/accepted/payment/paid/{lab_id}", response_model=list[TestRequestOut], tags=["Test Requests"])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_accepted_requests(lab_id: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all lab test requests that have been accepted AND whose payment has been marked as "Paid" for a specific lab.

    **Query Parameters:** lab_id (str, required): ID of the laboratory to filter accepted requests.

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
        .filter(model.LabTestRequest.status == "Accepted", model.LabTestBilling.payment_status == "Paid", model.LabTestRequest.lab_id == lab_id).all()

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
        
        # if not updated_request.locked_by:
        #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Cannot update status as the request {req_id} is not locked by any technician.")
        
        # if updated_request.locked_by != status_update.user_id:
        #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Cannot update status as the request {req_id} is locked by another technician.")
        
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


@router.get("/requests/take_test_parameters/{nic}/{test_req_id}/{test_name}", response_model=list[LabTestBase], tags=["Test Requests"])
@limiter.limit("15/minute")  # Limit to 10 requests per minute per IP
def get_test_parameters(nic: str ,test_req_id: int, test_name: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
        Retrieve test parameters for a specific test request, base on the specific patient gender, and age.

        *Add test Result*

        **Request Body (`ShowLabTestParams`):**
        - `nic` (str, required): The NIC/CNIC of the patient for whom the test parameters are being requested.
        - `test_req_id` (int, required): The ID of the test request for
            which parameters are being requested.
        - `test_name` (str, required): The name of the test for which parameters are being requested.

        **Response (200 OK):**
        Returns a list of test parameter objects (`LabTestBase`) that match the requested test name and are appropriate for the patient's age and gender
        Each `LabTestBase` object contains:
        - `test_id` (int): Unique identifier for the lab test.
        - `test_code` (str): Code representing the lab test.
        - `test_name` (str): Name of the lab test.
        - `parameter` (str | None): Specific parameter of the test (e.g., "Hemoglobin", "Glucose").
        - `unit` (str | None): Unit of measurement for the parameter (e.g,"g/dL", "mg/dL").
        - `test_range` (str | None): Normal range for the parameter, which may vary based on age and gender (e.g., "13.5-17.5 g/dL" for adult   males, "12.0-15.5 g/dL" for adult females). 
    """
    test_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == test_req_id, model.LabTestRequest.nic == nic, model.LabTestRequest.test_name == test_name).first()
    if not test_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Test request with ID {test_req_id} not found for the given patient NIC and test name.")
    
    patient = db.query(model.Patient).filter(model.Patient.nic == nic).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patient with NIC {nic} not found.")
    
    if not patient.dob:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Patient date of birth is not set.")

    # Precise age calculation based on year, month and day
    today = datetime.now().date()
    dob = patient.dob.date() if isinstance(patient.dob, datetime) else patient.dob
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    gender = (patient.gender or "").strip().lower()

    lab_tests = db.query(model.LabTest).filter(
        func.trim(model.LabTest.test_name) == test_name.strip()
    ).all()
    if not lab_tests:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lab test with name {test_name} not found.")

    results: list[LabTestBase] = []
    for lab_test in lab_tests:
        lab_gender = (lab_test.gender or "").strip().lower()
        if lab_gender and lab_gender not in ("any", "both", "all") and gender and lab_gender != gender:
            continue

        if age < 18:
            test_range = lab_test.child_range
        else:
            test_range = lab_test.adult_range

        results.append({
            "test_id": lab_test.test_id,
            "test_code": lab_test.test_code,
            "test_name": lab_test.test_name,
            "parameter": lab_test.parameter,
            "unit": lab_test.unit,
            "test_range": test_range,
        })

    return results


@router.post("/results", status_code=status.HTTP_201_CREATED, tags=["Test Results"])
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def create_lab_result(payload: LabTestCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Create a lab result and its associated mini test results.

    *Add test Result*

    **Request Body (`LabTestCreate`):**
    - `user_id` (int, required): Technician ID creating the result.
    - `nic` (str, required): Patient NIC/CNIC.
    - `test_req_id` (int, required): Test request ID to attach the result.
    - `description` (str, optional): Overall lab result description.
    - `mini_test` (list, optional): Mini test result rows.
        Each item in the list should contain:
        - `mini_test_name` (str, required): Name of the mini test parameter (e.g., "Hemoglobin").
        - `normal_range` (str, required): Normal range for the mini test (e.g., "13.5-17.5 g/dL").
        - `unit` (str, required): Unit of measurement for the mini test (e.g., "g/dL").
        - `value` (str, required): Result value for the mini test (e.g., "15.2").
    """
    test_request = db.get(model.LabTestRequest, payload.test_req_id)
    if not test_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Test request with ID {payload.test_req_id} not found.")

    if test_request.nic != payload.nic:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test request NIC does not match the provided NIC.")

    if not db.get(model.User, payload.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {payload.user_id} not found.")

    try:
        result = model.LabResult(
            user_id=payload.user_id,
            test_req_id=payload.test_req_id,
            description=payload.description,
        )
        db.add(result)
        db.flush()

        mini_tests = []
        if payload.mini_test:
            for item in payload.mini_test:
                mini_tests.append(model.MiniLabResult(
                    result_id=result.result_id,
                    mini_test_name=item.mini_test_name,
                    normal_range=item.normal_range,
                    unit=item.unit,
                    result_value=item.value,
                ))
            db.add_all(mini_tests)

        db.commit()
        return {
            "message": "Lab result created successfully",
            "result_id": result.result_id,
            "mini_test_count": len(mini_tests),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")


@router.get("/results/{result_id}", response_model=LabResultOut, tags=["Test Results"])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_lab_result(result_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve a lab result with its mini test results.
    *show test Result*

    **Path Parameters:**
    - `result_id` (int, required): Lab result ID to fetch.

    **Response (200 OK):**
    Returns a lab result object containing:
    - `result_id` (int): Unique identifier for the lab result.
    - `user_id` (int): ID of the technician who created the result.
    - `test_req_id` (int): ID of the associated test request.
    - `description` (str | None): Overall description of the lab result.
    - `created_at` (datetime): Timestamp when the lab result was created.
    - `mini_test` (list[MiniLabResultOut]): List of mini test results associated with this lab result. Each item contains:

        - `mini_test_id` (int): Unique identifier for the mini test result.
        - `result_id` (int): ID of the parent lab result.
        - `mini_test_name` (str): Name of the mini test parameter (e.g., "Hemoglobin").
        - `normal_range` (str): Normal range for the mini test (e.g., "13.5-17.5 g/dL").
        - `unit` (str): Unit of measurement for the mini test (e.g., "g/dL").
        - `result_value` (str): Result value for the mini test (e.g., "15.2").

    """
    result = db.get(model.LabResult, result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lab result with ID {result_id} not found.")

    return result

# @router.put("/requests/lock_test_request/visit_id/{visit_id}/user_id/{user_id}", response_model=list[TestRequestOut], tags=["Test Requests"])
# @limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
# def lock_test_request(visit_id: str, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
#     """
#     Lock a lab test request to a specific technician to prevent concurrent processing.

#     **Path Parameters:**
#     - `visit_id` (str, required): Visit ID whose related test requests should be locked.
#     - `user_id` (int, required): ID of the technician locking the requests.

#     **Response (200 OK):**
#     Returns `list[TestRequestOut]` with `locked_by` set to `user_id`
#     and `locked_at` set to the current timestamp.

#     **Constraints:**
#     - If the request is already locked by a different technician, the lock is rejected.
#     - A technician can re-lock their own already-locked request.

#     **Error Responses:**
#     - `403 Forbidden`: The test request is already locked by a different technician
#     - `404 Not Found`: No test requests exist with the given `visit_id`
#     - `404 Not Found`: User (Technician) ID not found

#     **Rate Limit:**
#     - 15 requests per minute per client IP.
#     """
    
#     if not db.get(model.User, user_id):
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
#     current_requests = db.query(model.LabTestRequest).filter(model.LabTestRequest.vid == visit_id).all()
#     if not current_requests:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit Id not found")
    
#     for current_request in current_requests:

#         # is the page is locked and it is not locked by you, then error. if it is locked by you, then ok.
#         if current_request.locked_by and current_request.locked_by != user_id:
#             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This page is already locked by another technician.")
            
#         current_request.locked_by = user_id
#         current_request.locked_at = datetime.now()

#     db.commit()        
#     return current_requests

# @router.put("/requests/unlock_test_request/visit_id/{visit_id}/user_id/{user_id}", response_model=list[TestRequestOut], tags=["Test Requests"])
# @limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
# def unlock_test_request(visit_id: str, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
#     """
#     Unlock a lab test request to release it from a technician's hold.

#     **Path Parameters:**
#         - `visit_id` (str, required): Visit ID whose related test requests should be unlocked.
#         - `user_id` (int, required): ID of the technician requesting the unlock.

#     **Response (200 OK):**
#         Returns `list[TestRequestOut]` after unlocking (`locked_by = null`, `locked_at = null`).

#     **Constraints:**
#     - If the request is locked by a different technician, the unlock is rejected.

#     **Behavior:**
#     - Sets `locked_by = None` and `locked_at = None` for each matched request.

#     **Error Responses:**
#     - `403 Forbidden`: The test request is locked by a different technician
#     - `404 Not Found`: No test requests exist with the given `visit_id`
#     - `404 Not Found`: User (Technician) ID not found.

#     **Rate Limit:**
#     - 15 requests per minute per client IP.
#     """
#     if not db.get(model.User, user_id):
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
#     current_requests = db.query(model.LabTestRequest).filter(model.LabTestRequest.vid == visit_id).all()
#     if not current_requests:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit Id not found")
    
#     for current_request in current_requests:

#         # if not current_request.locked_by: # if page is not locked, then you cannot unlock this page.
#         #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page is not locked")
        
#         if current_request.locked_by != user_id:
#             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page is not locked by this user: {user_id}")
            
#         current_request.locked_by = None
#         current_request.locked_at = None

#     db.commit()
    
#     return current_requests
