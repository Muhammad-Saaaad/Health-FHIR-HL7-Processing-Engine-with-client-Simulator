from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session, joinedload

from database import get_db
import model
from schemas.patient_schema import PatientBase, PatientDetail, WaitingListPatient
from rate_limiting import limiter

router = APIRouter(tags=["patient"])

@router.get("/get_patients", response_model=list[PatientBase])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_all_patients(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all patients registered in the LIS system.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of all patient records. Each object includes patient details
    as defined by the `GetPatient` schema (e.g., `pid`, `mpi`, `fname`, `lname`, `dob`, `gender`).

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

@router.get("/patient-waiting-list", response_model=list[WaitingListPatient])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def get_pending_requests(request: Request, response: Response, db: Session = Depends(get_db)):
    """ 
    Retrieve pending lab test requests, keeping only one row per `vid`.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of unique waiting-list entries for requests with `status == "Pending"`.
    If multiple pending rows share the same `vid`, only the first one is returned.
    Each object includes:
    - `test_req_id`, `mpi`, `fname`, `lname`, `status`, `date`, `vid`, `age`, `gender`.

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
            waiting_list_patient = WaitingListPatient(
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