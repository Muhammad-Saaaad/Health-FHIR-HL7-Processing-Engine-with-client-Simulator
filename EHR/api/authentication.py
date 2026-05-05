import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from rate_limiting import limiter
from schemas import auth_schema as schema
import model

router = APIRouter(tags=['Authentication'])

logger = logging.getLogger("ehr_authentication")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/authentication.log", maxBytes=1000000, backupCount=2)
handler.setFormatter(formatter)
logger.addHandler(handler)

@router.post("/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_doctor(doctor: schema.SignUp, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Register a new doctor in the EHR system.

    **Request Body:**
    - `name` (str, required): Doctor's full name.
    - `email` (str, required): Doctor's email address. Must be unique across all doctors.
    - `password` (str, required): Secure password for authentication.

    **Response (201 Created):**
    Returns a JSON confirmation message:
    ```json
    {
      "message": "data inserted successfully"
    }
    ```

    **Request Schema (`schema.SignUp`):**
    - `name` (str)
    - `email` (EmailStr)
    - `password` (str)

    **Constraints:**
    - Email must be unique. Attempting to register with a duplicate email will raise an error.

    **Error Responses:**
    - `400 Bad Request`: Database error or duplicate email detected
    """
    try:
        logger.info(f"Signup request received for email: {doctor.email}")
        new_doctor = model.Doctor(
            name = doctor.name,
            email = doctor.email,
            password = doctor.password
        )
        db.add(new_doctor)
        # db.flush()

        db.commit()
        db.refresh(new_doctor)
        logger.info(f"Doctor created successfully with ID: {new_doctor.doctor_id}, email: {doctor.email}")
        return JSONResponse(content={"message": "data inserted successfully"})
    except Exception as e:
        logger.error(f"Error creating doctor account for email {doctor.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.post("/login", status_code=status.HTTP_200_OK, response_model=schema.DoctorResponse)
@limiter.limit("20/minute")
def login_doctor(doctor: schema.Login, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Authenticate a doctor and log in to the EHR system.

    **Request Body:**
    - `email` (str, required): The doctor's registered email address.
    - `password` (str, required): The doctor's password.

    **Response (200 OK):**
    Returns the authenticated doctor object with the following fields:
    - `doctor_id` (int): Unique identifier for the doctor
    - `name` (str): Doctor's full name
    - `email` (str): Doctor's registered email address
    - `password` (str): Doctor's password
    - `specialization` (str, nullable): Medical specialization of the doctor
    - `date_join` (datetime): Timestamp when doctor registered in system
    - `about` (str, nullable): Brief bio or description about the doctor
    - `phone_no` (str, nullable): Doctor's phone number

    **Example Response:**
    ```json
    {
      "name": "saim",
      "password": "1234",
      "date_join": "2026-03-05T23:27:55.547000",
      "about": null,
      "doctor_id": 2,
      "email": "saim0067@gmail.com",
      "specialization": null,
      "phone_no": null
    }
    ```

    **Error Responses:**
    - `404 Not Found`: Email is not registered in the system
    - `404 Not Found`: Password does not match the registered email
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        logger.info(f"Login attempt for email: {doctor.email}")
        is_valid_doc = db.query(model.Doctor).filter(
            model.Doctor.email == doctor.email).first()
    except Exception as e:
        logger.error(f"Database error during login for email {doctor.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        
    if not is_valid_doc:
        logger.warning(f"Login failed - email not found: {doctor.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
    
    if is_valid_doc.password != doctor.password:
        logger.warning(f"Login failed - invalid password for email: {doctor.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")
    
    logger.info(f"Successful login for doctor ID: {is_valid_doc.doctor_id}, email: {doctor.email}")
    return is_valid_doc

@router.get("/get-all-doctors/", status_code=status.HTTP_200_OK, response_model=list[schema.DoctorResponse])
def get_all_doctors(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all registered doctors.

    **Response (200 OK):**
    Returns a JSON array of doctor records from the database. Each item contains:
    - `doctor_id` (int): Unique identifier for the doctor
    - `name` (str): Doctor's full name
    - `email` (str): Doctor's registered email address
    - `password` (str): Doctor's password
    - `specialization` (str, nullable): Medical specialization of the doctor
    - `date_join` (datetime): Timestamp when doctor registered in system
    - `about` (str, nullable): Brief bio or description about the doctor
    - `phone_no` (str, nullable): Doctor's phone number

    **Example Response:**
    ```json
    [
      {
        "name": "saim",
        "password": "1234",
        "date_join": "2026-03-05T23:27:55.547000",
        "about": null,
        "doctor_id": 2,
        "email": "saim0067@gmail.com",
        "specialization": null,
        "phone_no": null
      }
    ]
    ```

    **Error Responses:**
    - `400 Bad Request`: Unexpected database or server error.
    """
    try:
        logger.info("Fetching all doctors from database")
        doctors = db.query(model.Doctor).all()
        logger.info(f"Retrieved {len(doctors)} doctors from database")
        return doctors
    except Exception as e:
        logger.error(f"Error retrieving all doctors: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
    

@router.get("/get-doctor/{doc_id}", status_code=status.HTTP_200_OK, response_model=schema.DoctorResponse)
@limiter.limit("40/minute")
def get_doctor(doc_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve a doctor's record by their ID.

    **Path Parameters:**
    - `doc_id` (int, required): The unique database ID of the doctor.

    **Response (200 OK):**
    Returns the full doctor object with the following fields:
    - `doctor_id` (int): Unique identifier for the doctor
    - `name` (str): Doctor's full name
    - `email` (str): Doctor's registered email address
    - `password` (str): Doctor's password
    - `specialization` (str, nullable): Medical specialization of the doctor
    - `date_join` (datetime): Timestamp when doctor registered in system
    - `about` (str, nullable): Brief bio or description about the doctor
    - `phone_no` (str, nullable): Doctor's phone number

    **Example Response:**
    ```json
    {
      "name": "saim",
      "password": "1234",
      "date_join": "2026-03-05T23:27:55.547000",
      "about": null,
      "doctor_id": 2,
      "email": "saim0067@gmail.com",
      "specialization": null,
      "phone_no": null
    }
    ```

    **Error Responses:**
    - `404 Not Found`: No doctor exists with the given `doc_id`
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        logger.info(f"Fetching doctor with ID: {doc_id}")
        doctor = db.get(model.Doctor, doc_id)
        if doctor is None:
            logger.warning(f"Doctor not found with ID: {doc_id}")
        else:
            logger.info(f"Retrieved doctor with ID: {doc_id}, email: {doctor.email}")
        return doctor
    except Exception as e:
        logger.error(f"Error retrieving doctor with ID {doc_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        

@router.put("/change-doctor/{doc_id}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
def alter_phone_no(doc_id: int, doctor: schema.DoctorUpdate, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Update doctor information (phone number, specialization, and about).

    **Path Parameters:**
    - `doc_id` (int, required): The unique ID of the doctor to update.

    **Request Body:**
    - `phone_no` (str, optional): Doctor's phone number.
    - `specialization` (str, optional): Doctor's medical specialization.
    - `about` (str, optional): Doctor's bio or description.

    **Response (202 Accepted):**
    Returns a JSON confirmation message:
    ```json
    {
      "message": "Doctor updated successfully"
    }
    ```

    **Error Responses:**
    - `404 Not Found`: No doctor exists with the given `doc_id`
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        logger.info(f"Updating phone number for doctor ID: {doc_id}")
        doc = db.query(model.Doctor).filter(model.Doctor.doctor_id == doc_id).first()

        if not doc:
            logger.warning(f"Doctor not found for phone number update with ID: {doc_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="doctor id not valid")
        
        doc.phone_no = doctor.phone_no
        doc.about = doctor.about
        doc.specialization = doctor.specialization

        db.add(doc)
        db.commit()
        logger.info(f"Doctor successfully updated for doctor ID: {doc_id}")

        return {'message': "Doctor updated successfully"}

    except Exception as e:
        logger.error(f"Error updating phone number for doctor ID {doc_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
