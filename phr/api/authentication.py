from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas import auth_schema, patient_schema
from database import get_db
import model

router = APIRouter(tags=['Authentication'])

@router.post("/signup", status_code=status.HTTP_201_CREATED)
def SignUP_patient(patient: auth_schema.SignUp, db :Session = Depends(get_db)):
    """
    Set a password for an existing patient in the PHR system.

    A patient record is pre-created by the system when they register via the EHR.
    This endpoint allows the patient to set their password to activate their PHR account.

    **Request Body:**
    - `nic` (str, required): The patient's National Identity Card (NIC) number. Must already
      exist in the system — patients cannot self-register.
    - `password` (str, required): The password the patient wants to set for their account.

    **Response (201 Created):**
    Returns a JSON message:
    - `message`: "Sign Up sucessfully"

    **Constraints:**
    - The NIC must already exist in the Patient table. If not found, sign-up is rejected.

    **Error Responses:**
    - `409 Conflict`: No patient found with the provided NIC (patient does not exist)
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        is_valid_patient = db.query(model.Patient).filter(model.Patient.nic == patient.nic).first()

        if not is_valid_patient:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user does not exists")

        is_valid_patient.password = patient.password

        db.commit()
        db.refresh(is_valid_patient)
        return JSONResponse(content={"message": "Sign Up sucessfully"})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.post("/login",status_code=status.HTTP_200_OK, response_model=patient_schema.Patient)
def login_patient(patient: auth_schema.Login, db :Session = Depends(get_db)):
    """
        Authenticate a patient and log in to the PHR (Personal Health Record) system.

        **Request Body:**
        - `nic` (str, required): The patient's National Identity Card (NIC) number.
        - `password` (str, required): The patient's password (set during sign-up).

        **Response (200 OK):**
        Returns a JSON object containing:
        - `patient` (object): Patient information
        - `mpi` (int): Master Patient Index - unique identifier
        - `nic` (str): National Identity Card number
        - `name` (str): Patient's full name
        - `phone_no` (str | null): Contact phone number
        - `gender` (str): Patient's gender
        - `date_of_birth` (date): Date of birth (format: YYYY-MM-DD)
        - `address` (str | null): Residential address

        **Example Response:**
        ```json
        {
        "patient": {
            "mpi": 12345,
            "nic": "1234567890V",
            "name": "John Doe",
            "phone_no": "+92-300-1234567",
            "gender": "Male",
            "date_of_birth": "1990-05-15",
            "address": "123 Main Street, Rawalpindi"
        }
        }
        ```

        **Error Responses:**
        - `404 Not Found`: NIC is not registered in the system
        ```json
        {"detail": "NIC not found"}
        ```
        - `404 Not Found`: Password does not match the one set for this NIC
        ```json
        {"detail": "Invalid password"}
        ```
        - `400 Bad Request`: Unexpected database or server error
        ```json
        {"detail": "Database error"}
        ``` 
    """
    try:
        is_valid_patient = db.query(model.Patient).filter(
            model.Patient.nic == patient.nic).first()
        
        if not is_valid_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="nic not valid")
        
        if is_valid_patient.password != patient.password:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")
        
        return is_valid_patient
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")