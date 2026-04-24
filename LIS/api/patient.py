from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session, joinedload

from database import get_db
import model
from schemas.patient_schema import PatientBase, PatientDetail, WaitingPatientList, AcceptedPatientList
from rate_limiting import limiter

router = APIRouter(tags=["patient"])

@router.get("/get_patients", response_model=list[PatientBase])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_all_patients(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all patients registered in the LIS system.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns `list[PatientBase]`. Each patient object includes:
    - `mpi` (int)
    - `fname` (str)
    - `lname` (str)
    - `updated_at` (str, formatted date)

    **Note:**
    - Returns an empty list if no patients exist in the system.
    """
    patients = db.query(model.Patient).all()
    return patients

@router.get("/patients/{mpi}", response_model=PatientDetail)
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_patient_detail(mpi: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
        Retrieve detailed patient information and associated lab reports.

        **Path Parameters:**
        - `mpi` (int, required): Master Patient Index (primary key) used to identify the patient.

        **Response (200 OK):**
        Returns a merged patient detail object with:
        - `mpi` (int): Patient MPI.
        - `fname` (str): First name.
        - `lname` (str): Last name.
        - `gender` (str): Gender value stored in LIS.
        - `age` (str): Computed from DOB and serialized as `"<years> years"`.
        - `updated_at` (str): Last update timestamp serialized by schema.
        - `lab_reports` (list[object]): Patient lab test summaries, each containing:
            - `report_id` (int): Lab test request ID.
            - `test_name` (str): Name of requested test.
            - `vid` (int | None): Visit ID linked to the test request.
            - `status` (str): Current test/request status.

        **Error Responses:**
        - `404 Not Found`: Patient with provided MPI was not found.
        - `429 Too Many Requests`: Rate limit exceeded (`20/minute`).
        - `500 Internal Server Error`: Unexpected unhandled server/database error.
    """
    patient = db.get(model.Patient, mpi)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    response = {
        "mpi": patient.mpi,
        "fname": patient.fname,
        "lname": patient.lname,
        "gender": patient.gender,
        "age": patient.dob
    }

    lab_details = db.query(model.LabTestRequest).filter(model.LabTestRequest.mpi == mpi).all()
    reports = [
        {
            "report_id": lab_detail.test_req_id,
            "test_name": lab_detail.test_name,
            "vid": lab_detail.vid,
            "status": str(lab_detail.status).capitalize()
        } for lab_detail in lab_details if lab_detail.status in ("Completed", "Accepted", "accepted", "completed")
    ]

    response["lab_reports"] = reports
    return response

@router.get("/patient-waiting-list", response_model=list[WaitingPatientList])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_pending_requests(request: Request, response: Response, db: Session = Depends(get_db)):
    """ 
    Retrieve pending lab test requests, keeping only one row per `vid`.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of unique waiting-list entries for requests with `status == "Pending"`.
    If multiple pending rows share the same `vid`, only the first one is returned.
    Each object is `WaitingPatientList` with:
    - `test_req_id` (int)
    - `vid` (str | null)
    - `mpi` (int)
    - `fname` (str)
    - `lname` (str)
    - `status` (str)
    - `date` (str, formatted date)

    **Note:**
    - Returns an empty list if there are no pending test requests.
    - Uniqueness is based on `vid`.
    """
    pending_requests = db.query(model.LabTestRequest).filter(model.LabTestRequest.status == "Pending").all()
    waiting_list_patients = []
    seen_vids = set()

    for req in pending_requests:
        if req.vid in seen_vids:
            continue

        patient = db.get(model.Patient, req.mpi)
        if patient:
            seen_vids.add(req.vid)
            waiting_list_patient = WaitingPatientList(
                test_req_id=req.test_req_id,
                mpi=patient.mpi,
                fname=patient.fname,
                lname=patient.lname,
                status=req.status,
                date=req.created_at,
                vid=req.vid,
            )
            waiting_list_patients.append(waiting_list_patient)

    return waiting_list_patients

@router.get("/patient-process/{mpi}/{vid}", response_model=PatientDetail)
@limiter.limit("20/minute")
def get_patient_process(mpi: int, vid: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve a pending patient-processing view for a specific visit.

    This endpoint is intended for the LIS processing workflow where pending
    test requests are pulled by visit ID and combined with patient demographics.

    **Path Parameters:**
    - `mpi` (int, required): Master Patient Index (primary key of `patient`).
    - `vid` (str, required): Visit ID used to locate pending test requests.

    **Response (200 OK):**
    Returns `PatientDetail` with:
    - `mpi` (int)
    - `fname` (str)
    - `lname` (str)
    - `gender` (str)
    - `age` (str): Serialized from DOB (for example, `"31 years"`).
    - `lab_reports` (list[`LabBase`]): Pending tests for the provided `vid`, each containing:
        - `report_id` (int | null): Test request ID.
        - `test_name` (str | null): Requested test name.
        - `vid` (str | null): Visit ID.
        - `status` (str | null): Request status (capitalized in response).

    **Error Responses:**
    - `404 Not Found`: No pending tests found for the given `vid`.
    - `404 Not Found`: Patient with provided `mpi` does not exist.
    - `429 Too Many Requests`: Rate limit exceeded (`20/minute`).
    - `500 Internal Server Error`: Unexpected unhandled server/database error.
    """

    lab_tests = db.query(model.LabTestRequest).filter(model.LabTestRequest.vid == vid, model.LabTestRequest.status == "Pending").all()
    if not lab_tests:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Visit ID {vid} not found.")
    
    patient =db.get(model.Patient, mpi) 
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Patient with MPI {mpi} not found.")
    
    lab_details = []
    for lab_test in lab_tests:
        lab_details.append({
            "report_id": lab_test.test_req_id,
            "test_name": lab_test.test_name,
            "vid": lab_test.vid,
            "status": str(lab_test.status).capitalize()
        })

    response = PatientDetail(
        mpi=mpi,
        fname=patient.fname,
        lname=patient.lname,
        gender=patient.gender,
        age=patient.dob,
        lab_reports=lab_details
    )

    return response    

@router.get("/patient-Accepted-list", response_model=list[AcceptedPatientList])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_accepted_requests(request: Request, response: Response, db: Session = Depends(get_db)):
    """ 
    Retrieve accepted lab test requests, keeping only one row per `vid`.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of unique waiting-list entries for requests with `status == "Accepted"`.
    If multiple accepted rows share the same `vid`, only the first one is returned.
    Each object is `AcceptedPatientList` with:
    - `test_req_id` (int)
    - `test_name` (str)
    - `vid` (str | null)
    - `mpi` (int)
    - `fname` (str)
    - `lname` (str)
    - `status` (str)
    - `date` (str, formatted date)

    **Note:**
    - Returns an empty list if there are no accepted test requests.
    - Uniqueness is based on `vid`.
    """
    accepted_requests = db.query(model.LabTestRequest).filter(model.LabTestRequest.status == "Accepted").all()
    patients_accepted_list = []

    for req in accepted_requests:

        patient = db.get(model.Patient, req.mpi)
        if patient:
            waiting_list_patient = AcceptedPatientList(
                test_req_id=req.test_req_id,
                test_name=req.test_name,
                mpi=patient.mpi,
                fname=patient.fname,
                lname=patient.lname,
                status=req.status,
                date=req.created_at,
                vid=req.vid,
            )
            patients_accepted_list.append(waiting_list_patient)

    return patients_accepted_list