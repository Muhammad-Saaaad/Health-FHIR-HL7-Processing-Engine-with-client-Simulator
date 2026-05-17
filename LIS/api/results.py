import asyncio
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import desc, func

from database import get_db
import model
from schemas.result_schema import TestResultOut, MiniTestOut, CompleteTestResultCreate
from schemas.lab_schema import LabTestBase  
from rate_limiting import limiter
from .engine_service import send_to_engine

router = APIRouter(tags=["Results"])

logger = logging.getLogger("results")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/results.log", maxBytes=1000000, backupCount=1)
handler.setFormatter(formatter)
logger.addHandler(handler)


@router.post("/results/complete", status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def add_complete_result(r_in: CompleteTestResultCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Submit a complete lab result for an accepted test request.

    **Request Body:**
    - `user_id` (int, required): ID of the lab technician submitting the result. Must be a valid user.
    - `lab_id` (str, required): ID of the lab submitting the result.
    - `test_req_id` (int, required): ID of the test request this result belongs to. Must exist and be accepted.
    - `test_code` (int | str, required): Code representing the type of test being submitted.
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
    - Sends or queues an HL7 result message for the InterfaceEngine.

    **Constraints:**
    - `lab_id` must refer to a valid lab.
    - `user_id` must refer to a valid technician in the User table.
    - `test_req_id` must refer to an existing test request with `status == "Accepted"`.
    - Only one result can be submitted per test request (no duplicate results).

    **Error Responses:**
    - `400 Bad Request`: Lab ID is invalid
    - `404 Not Found`: User (Technician) ID not found
    - `404 Not Found`: Test Request not found
    - `404 Not Found`: Test request status is not "Accepted"
    - `400 Bad Request`: A result has already been submitted for this test request

    **Rate Limit:**
    - 15 requests per minute per client IP.
    """
    print("come here")
    lab = db.get(model.Lab, r_in.lab_id)
    if not lab:
        logger.error(f"Invalid lab ID provided: {r_in.lab_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid lab ID")
    
    if not db.get(model.User, r_in.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
        
    req = db.get(model.LabTestRequest, r_in.test_req_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test Request not found.")
    
    if req.status != "Accepted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="test req is not accepted.")
    
    # if db.query(model.LabTestBilling) \
    #     .filter(model.LabTestBilling.test_req_id == r_in.test_req_id).first().payment_status != "Paid":

    #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not paid.")

    labtest = db.query(model.LabTest).filter(model.LabTest.test_code == r_in.test_code).first()
    if not labtest:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid test code provided.")
        
    if db.query(model.LabResult).filter(model.LabResult.test_req_id == r_in.test_req_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Result already submitted for this request.")

    try:
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
                    mini_test_name = mini_test_data.test_name,
                    normal_range = mini_test_data.normal_range,
                    unit = mini_test_data.units,
                    result_value = mini_test_data.result_value
                )
            )
        db.add_all(db_mini_tests)

        msg_id = str(uuid4())
        date_str = datetime.now().strftime("%Y%m%d%H%M%S")

        hl7_msg = f"""MSH|^~\\&|LIS||EHR||{date_str}||ORU^R01|{msg_id}|P|2.3\n"""
        hl7_msg = f"PID|1||{req.nic}\n"
        hl7_msg += f"""OBR|1|{req.vid}||{r_in.test_code}^{labtest.test_name}^{r_in.description}|||||||||||\n"""  

        for idx, mini_test in enumerate(r_in.mini_tests):
            hl7_msg += f"""OBX|{idx + 1}||{mini_test.test_name}||{mini_test.result_value}|{mini_test.units}|{mini_test.normal_range}|||F\n"""

        # 4. Update TestRequest status to Completed
        config_data= db.query(model.Config).filter(model.Config.sent_to_engine == False) \
                .order_by(desc(model.Config.config_id)).first()
        
        if config_data and config_data.hold_flag: # if we have to hold the data
            history_hospital = config_data.history.get(lab.name, {})

            if history_hospital:
                history_hospital["submit-lab-result"] = history_hospital.get("submit-lab-result", 0) + 1
            else:
                config_data.history[lab.name] = history_hospital
                config_data.history[lab.name]["submit-lab-result"] = 1
            
            endpoint_already_added = False
            for endpoint in config_data.data:
                if endpoint.get("system_id") == lab.lab_id and endpoint.get("/submit-lab-result"): # if endpoint exists in config.
                    endpoint["/submit-lab-result"].append(hl7_msg)
                    endpoint_already_added = True
                    break
            
            if not endpoint_already_added:
                config_data.data.append(
                    {   
                        "system_id": lab.lab_id,
                        "/submit-lab-result": [hl7_msg]
                    }
                )

            flag_modified(config_data, "history")
            flag_modified(config_data, "data")

            req.status = "Completed"
            db.add(req)
            db.commit()
            logger.info(f"Data added to config for lab {lab.name} due to hold flag. Current history: {config_data.history}")
            return {"message": "data added to config due to hold flag"}
        
        asyncio.create_task(send_to_engine(hl7_msg, "http://127.0.0.1:9000/submit-lab-result", lab.lab_id)) # send the data to engine asynchronously.

        req.status = "Completed"
        db.add(req)
        db.commit()
        return {"message": "result added"}
    except Exception as exp:
        db.rollback()
        logger.error(f"Error adding complete result: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

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


@router.get("/requests/take_test_parameters/{nic}/{test_req_id}", response_model=list[LabTestBase])
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


# @router.put("/requests/lock_test/{test_req_id}/user_id/{user_id}", response_model=TestRequestOut)
# @limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
# def lock_test_request(test_req_id: int, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
#     """
#     Lock a lab test request to a specific technician to prevent concurrent processing.

#     **Path Parameters:**
#     - `test_req_id` (int, required): Test request ID to lock.
#     - `user_id` (int, required): ID of the technician locking the request.

#     **Response (200 OK):**
#     Returns the updated test request with `locked_by` set to `user_id`
#     and `locked_at` set to the current timestamp.

#     **Constraints:**
#     - If the request is already locked by a different technician, the lock is rejected.
#     - A technician can re-lock their own already-locked request.

#     **Error Responses:**
#     - `403 Forbidden`: The test request is already locked by a different technician
#     - `404 Not Found`: No test requests exist with the given `test_req_id`
#     - `404 Not Found`: User (Technician) ID not found

#     **Rate Limit:**
#     - 15 requests per minute per client IP.
#     """
    
#     if not db.get(model.User, user_id):
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
#     current_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == test_req_id).first()
#     if not current_request:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test request not found.")
    
#     # is the page is locked and it is not locked by you, then error. if it is locked by you, then ok.
#     if current_request.locked_by and current_request.locked_by != user_id:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This page is already locked by another technician.")
            
#     current_request.locked_by = user_id
#     current_request.locked_at = datetime.now()

#     db.commit()        
#     return current_request

# @router.put("/requests/unlock_test_request/test_req_id/{test_req_id}/user_id/{user_id}", response_model=TestRequestOut)
# @limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
# def unlock_test_request(test_req_id: int, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
#     """
#     Unlock a lab test request to release it from a technician's hold.

#     **Path Parameters:**
#         - `test_req_id` (int, required): Test request ID to unlock.
#         - `user_id` (int, required): ID of the technician requesting the unlock.

#     **Response (200 OK):**
#         Returns the updated test request after unlocking.

#     **Constraints:**
#     - If the request is locked by a different technician, the unlock is rejected.

#         **Behavior:**
#     **Behavior:**
#     - Sets `locked_by = None` and `locked_at = None` for the request.

#     **Error Responses:**
#     - `403 Forbidden`: The test request is locked by a different technician
#     - `404 Not Found`: No test requests exist with the given `test_req_id`
#     - `404 Not Found`: User (Technician) ID not found.

#     **Rate Limit:**
#     - 15 requests per minute per client IP.
#     """
#     if not db.get(model.User, user_id):
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
    
#     current_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == test_req_id).first()
#     if not current_request:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test request not found.")
    
#     if current_request.locked_by != user_id:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page is not locked by this user: {user_id}")
            
#     current_request.locked_by = None
#     current_request.locked_at = None

#     db.commit()
    
#     return current_request
