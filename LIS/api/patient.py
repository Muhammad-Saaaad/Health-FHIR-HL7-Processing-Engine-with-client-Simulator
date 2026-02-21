from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.patient_schema import GetPatient

router = APIRouter(tags=["patient"])

@router.get("/get_patients", response_model=list[GetPatient], tags=["patient"])
def get_all_patients(db: Session = Depends(get_db)):
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

@router.get("/patients/{pid}", response_model=GetPatient, tags=["patient"])
def get_patient_detail(pid: int, db: Session = Depends(get_db)):
    """
    Retrieve detailed information about a specific patient by their internal patient ID.

    **Path Parameters:**
    - `pid` (int, required): The internal patient ID (primary key) to look up.

    **Response (200 OK):**
    Returns the patient record matching the given `pid`, including fields such as
    `mpi`, `fname`, `lname`, `dob`, and `gender`.

    **Error Responses:**
    - `404 Not Found`: No patient exists with the given `pid`
    - `500 Internal Server Error`: Unexpected database error (FastAPI default for unhandled DB exceptions)
    """
    patient = db.get(model.Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient