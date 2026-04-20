import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, HTTPException, Depends, Response, Request
from sqlalchemy.orm import Session, joinedload

from database import get_db
import model
from rate_limiting import limiter
from schemas.doctor_schema import DoctorBase

router = APIRouter(tags=["Doctors"])

# Configure logging
logger = logging.getLogger("phr_api_doctor")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    r"logs/doctor.log", 
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=2
)
handler.setFormatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
logger.addHandler(handler)


@router.get("/all_doctors",response_model=list[DoctorBase])
@limiter.limit("30/minute")
def get_doctors(request: Request, response: Response, db: Session = Depends(get_db)):
    """
        Retrieve all doctors available in the PHR system.

        Input:
        - No request body.
        - Uses request context and database session.

        Returns:
        - `200 OK` with list[`DoctorBase`].
        - Each item includes:
            - `doctor_id` (int)
            - `name` (str)
            - `phone_no` (str | null)
            - `specialization` (str | null)
            - `last_visit` (str, formatted date)

        Potential errors:
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        return db.query(model.Doctor).all()
    except Exception as exp:
        logger.error(f"Error fetching doctors: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.get("/single-doctor/{doctor_id}")
@limiter.limit("30/minute")
def get_doctor_by_id(request: Request, response: Response, doctor_id: int, db: Session = Depends(get_db)):
    """
        Retrieve one doctor by doctor ID.

        Input:
        - Path parameter:
            - `doctor_id` (int): Unique doctor identifier.
        - No request body.

        Returns:
        - `200 OK` with doctor object containing fields like:
            `doctor_id`, `name`, `phone_no`, `specialization`, `last_visit`, and profile fields.

        Potential errors:
        - `404 Not Found`: Doctor does not exist for the provided ID.
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        doctor = db.query(model.Doctor).filter(model.Doctor.doctor_id == doctor_id).first()
        if not doctor:
            logger.warning(f"Doctor with ID {doctor_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Doctor with the given ID {doctor_id} not found.")
        return doctor
    except Exception as exp:
        logger.error(f"Error fetching doctor with ID {doctor_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


@router.get("/doctor-encountered-by-patient/{mpi}", response_model=list[DoctorBase])
@limiter.limit("30/minute")
def get_doctor_encountered_by_patient(request: Request, response: Response, mpi: int, db: Session = Depends(get_db)):
    """
        Retrieve doctors encountered by a specific patient.

        Input:
        - Path parameter:
            - `mpi` (int): Patient MPI identifier.
        - No request body.

        Returns:
        - `200 OK` with list[`DoctorBase`] built from visit-note joins.
        - Each item contains `doctor_id`, `name`, `phone_no`, `specialization`, `last_visit`.
        - Empty list if patient has no encountered doctors.

        Potential errors:
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        joined_response = db.query(model.VisitingNotes).filter(model.VisitingNotes.mpi == mpi).options(
            joinedload(model.VisitingNotes.patient),
            joinedload(model.VisitingNotes.doctor)
        ).all()

        doctors =[
            {
                "doctor_id": doctor.doctor.doctor_id,
                "name": doctor.doctor.name,
                "phone_no": doctor.doctor.phone_no,
                "specialization": doctor.doctor.specialization,
                "last_visit": doctor.doctor.last_visit
            } for doctor in joined_response
        ]
        
        if doctors is []:
            logger.warning(f"This patient with MPI {mpi} has not encountered any doctor yet.")
        return doctors
    
    except Exception as exp:
        logger.error(f"Error fetching doctor with ID {mpi}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))