from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas import auth_schema, patient_schema
from database import get_db
import model
from rate_limiting import limiter

router = APIRouter(tags=['Authentication'])

@router.post("/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def SignUP_patient(patient: auth_schema.SignUp, request: Request, response: Response,  db :Session = Depends(get_db)):
    """
        Create a PHR password for an already-registered patient.

        Input:
        - Body (`auth_schema.SignUp`):
            - `nic` (str): Existing patient's NIC.
            - `password` (str): Password to set for the account.

        Returns:
        - `201 Created` with JSON:
            - `message` (str): Confirmation message.

        Request schema (`auth_schema.SignUp`):
        - `nic` (str)
        - `password` (str)

        Potential errors:   
        - `409 Conflict`: Patient with provided NIC does not exist.
        - `400 Bad Request`: Any unexpected database/server exception.
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
@limiter.limit("10/minute")
def login_patient(patient: auth_schema.Login, request: Request, response: Response, db :Session = Depends(get_db)):
    """
        Authenticate a patient in the PHR system.

        Input:
        - Body (`auth_schema.Login`):
            - `nic` (str): Patient NIC.
            - `password` (str): Account password.

        Returns:
        - `200 OK` with `patient_schema.Patient`:
            - `nic` (str), `name` (str), `phone_no` (str | null),
                `gender` (str), `date_of_birth` (date), `address` (str | null).

        Potential errors:
        - `404 Not Found`: NIC does not exist.
        - `404 Not Found`: Password is invalid for the NIC.
        - `400 Bad Request`: Any unexpected database/server exception.
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

@router.get("/hospitals/{nic}")
@limiter.limit("20/minute")
async def get_hospitals_for_patient(nic: str, request: Request, response: Response, db :Session = Depends(get_db)):
    """
        Retrieve a list of hospitals associated with a patient.

        Input:
        - Path parameter:
            - `nic` (str): Patient NIC.

        Returns:
        - `200 OK` with JSON:
            - `hospitals` (List[str]): List of hospital names associated with the patient.

        Potential errors:
        - `404 Not Found`: Patient with provided NIC does not exist.
        - `400 Bad Request`: Any unexpected database/server exception.
    """
    try:
        is_valid_patient = db.query(model.Patient).filter(model.Patient.nic == nic).first()

        if not is_valid_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient does not exists")

        hospital_names = [relation.hospital.name for relation in is_valid_patient.patient_relation]
        
        return {"hospitals": hospital_names}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")