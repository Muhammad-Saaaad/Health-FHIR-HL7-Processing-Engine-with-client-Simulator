from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas import auth_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Authentication'])

@router.post("/signup", status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: schema.SignUp, db :Session = Depends(get_db)):
    """
    Register a new doctor in the EHR system.

    **Request Body:**
    - `name` (str, required): Doctor's full name.
    - `email` (str, required): Doctor's email address. Must be unique across all doctors.
    - `password` (str, required): Secure password for authentication.

    **Response (201 Created):**
    Returns a JSON message:
    - `message`: "data inserted sucessfully"

    **Constraints:**
    - Email must be unique. Attempting to register with a duplicate email will raise an error.

    **Error Responses:**
    - `400 Bad Request`: Database error or duplicate email detected
    """
    try:
        new_doctor = model.Doctor(
            name = doctor.name,
            email = doctor.email,
            password = doctor.password
        )
        db.add(new_doctor)
        # db.flush()

        db.commit()
        db.refresh(new_doctor)
        return JSONResponse(content={"message": "data inserted sucessfully"})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.post("/login",status_code=status.HTTP_200_OK)
def login_doctor(doctor: schema.Login, db :Session = Depends(get_db)):
    """
    Authenticate a doctor and log in to the EHR system.

    **Request Body:**
    - `email` (str, required): The doctor's registered email address.
    - `password` (str, required): The doctor's password.

    **Response (200 OK):**
    Returns a JSON message on successful authentication:
    - `message`: "login sucessfully"

    **Error Responses:**
    - `404 Not Found`: Email is not registered in the system
    - `404 Not Found`: Password does not match the registered email
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        is_valid_doc = db.query(model.Doctor).filter(
            model.Doctor.email == doctor.email).first()
        
        if not is_valid_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
        
        if is_valid_doc.password != doctor.password:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")
        
        return {"message": "login sucessfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.get("/get-doctor/{email}/{password}", status_code=status.HTTP_200_OK)
def get_doctor(email: str, password: str, db: Session = Depends(get_db)):
    """
    Retrieve a doctor's record by verifying their email and password credentials.

    **Path Parameters:**
    - `email` (str, required): The doctor's registered email address.
    - `password` (str, required): The doctor's password for verification.

    **Response (200 OK):**
    Returns the full doctor object if credentials match, or `null` if no matching doctor is found.

    **Note:**
    - Credentials are passed as URL path segments. Consider using the POST /login endpoint for
      more secure authentication flows.

    **Error Responses:**
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        doctor = db.query(model.Doctor).filter(
            model.Doctor.email == email , model.Doctor.password == password).first()
        return doctor
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        

@router.put("/change-phone-no{p_no}/id{doc_id}", status_code=status.HTTP_202_ACCEPTED)
def alter_phone_no(p_no: str , doc_id: int, db :Session = Depends(get_db)):
    """
    Update the phone number of a registered doctor.

    **Path Parameters:**
    - `p_no` (str, required): The new phone number to assign to the doctor.
    - `doc_id` (int, required): The unique ID of the doctor whose phone number is being updated.

    **Response (202 Accepted):**
    Returns a JSON confirmation message:
    - `message`: "phone no added"

    **Error Responses:**
    - `404 Not Found`: No doctor exists with the given `doc_id`
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        doc = db.query(model.Doctor).filter(model.Doctor.doctor_id == doc_id).first()

        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="doctor id not valid")
        
        doc.phone_no = p_no

        db.commit()
        db.refresh(doc)

        return {'message': "phone no added"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
