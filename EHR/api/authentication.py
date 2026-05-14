import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

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

@router.post("/signup-admin", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_admin(admin: schema.Admin, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Register a new admin in the EHR system.

    **Request Body:**
    - `email` (EmailStr, required): Admin's email address.
    - `password` (str, required): Secure password for authentication.

    **Response (201 Created):**
    Returns a JSON confirmation message:
    ```json
    {
      "message": "Admin account created successfully"
    }
    ```

    **Request Schema (`schema.Admin`):**
    - `email` (EmailStr)
    - `password` (str)

    **Constraints:**
    - Role is automatically set to 2 (Admin).
    - Admin is created without a hospital_id (hospital_id = NULL).

    **Error Responses:**
    - `400 Bad Request`: Database error or validation error
    """
    logger.info(f"Admin signup request received for email: {admin.email}")
    if db.query(model.Users).filter(model.Users.email == admin.email).first():
        logger.warning(f"Admin signup failed - email already exists: {admin.email}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email already exists")

    try:
        new_admin = model.Users(
            email = admin.email,
            password = admin.password,
            roll=2
        )
        db.add(new_admin)
        db.commit()
        logger.info(f"Admin account created successfully with ID: {new_admin.users_id}, email: {admin.email}")
        return JSONResponse(content={"message": "Admin account created successfully"})
    except Exception as e:
        logger.error(f"Error creating admin account for email {admin.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.post("/login-admin", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def login_admin(admin: schema.Admin, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Authenticate an admin and log in to the EHR system.

    **Request Body:**
    - `email` (EmailStr, required): Admin's registered email address.
    - `password` (str, required): Admin's password.

    **Response (200 OK):**
    Returns the authenticated admin user object with the following fields:
    - `users_id` (int): Unique identifier for the admin
    - `email` (str): Admin's registered email address
    - `password` (str): Admin's password
    - `name` (str, nullable): Admin's full name
    - `hospital_id` (str, nullable): Associated hospital ID (typically NULL for admins)
    - `specialization` (str, nullable): Admin's specialization
    - `roll` (int): Role identifier (2 for Admin)
    - `date_join` (datetime): Timestamp when admin was registered
    - `about` (str, nullable): Admin's bio or description
    - `phone_no` (str, nullable): Admin's phone number

    **Request Schema (`schema.Admin`):**
    - `email` (EmailStr)
    - `password` (str)

    **Error Responses:**
    - `404 Not Found`: Email is not registered in the system
    - `404 Not Found`: Password does not match the registered email
    - `400 Bad Request`: Unexpected database or server error
    """
    
    try:
        is_valid_user = db.query(model.Users).filter(model.Users.email == admin.email, model.Users.roll == 2).first()
    except Exception as e:
        logger.error(f"Database error during login for email {admin.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        
    if not is_valid_user:
        logger.warning(f"Login failed - email not found: {admin.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
    
    if is_valid_user.password != admin.password:
        logger.warning(f"Login failed - invalid password for email: {admin.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")

    logger.info(f"Successful login for user ID: {is_valid_user.users_id}, email: {admin.email}")
    return is_valid_user

@router.post("/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def create_doctor(doctor: schema.SignUp, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Register a new doctor in the EHR system.

    **Request Body:**
    - `name` (str, required): Doctor's full name.
    - `email` (EmailStr, required): Doctor's email address.
    - `password` (str, required): Secure password for authentication.
    - `hospital_id` (str, required): The ID of the hospital where the doctor will work.

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
    - `hospital_id` (str)

    **Constraints:**
    - The combination of email and hospital_id must be unique. Same email can exist in different hospitals.
    - The specified hospital_id must exist in the system.

    **Error Responses:**
    - `404 Not Found`: Hospital ID does not exist in the system
    - `400 Bad Request`: Database error or validation error
    """
    logger.info(f"Signup request received for email: {doctor.email}")
    if db.get(model.Hospital, doctor.hospital_id) is None:
        logger.warning(f"Signup failed - hospital not found with ID: {doctor.hospital_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="hospital id not valid")

    if db.query(model.Users).filter(model.Users.email == doctor.email, model.Users.hospital_id == doctor.hospital_id).first():
        logger.warning(f"Signup failed - email already exists for hospital ID: {doctor.hospital_id}, email: {doctor.email}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email already exists for this hospital")

    try:
        new_user = model.Users(
            name = doctor.name,
            email = doctor.email,
            password = doctor.password,
            hospital_id = doctor.hospital_id,
            roll = 1
        )
        db.add(new_user)

        db.commit()
        db.refresh(new_user)
        logger.info(f"User created successfully with ID: {new_user.users_id}, email: {doctor.email}")
        return JSONResponse(content={"message": "data inserted successfully"})
    except Exception as e:
        logger.error(f"Error creating user account for email {doctor.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.post("/login", status_code=status.HTTP_200_OK, response_model=schema.DoctorResponse)
@limiter.limit("20/minute")
def login_doctor(doctor: schema.Login, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Authenticate a doctor and log in to the EHR system.

    **Request Body:**
    - `email` (EmailStr, required): The doctor's registered email address.
    - `password` (str, required): The doctor's password.
    - `hospital_id` (str, required): The hospital ID associated with the doctor.

    **Response (200 OK):**
    Returns the authenticated doctor object with the following fields:
    - `users_id` (int): Unique identifier for the doctor
    - `hospital_id` (str): The hospital ID associated with the doctor
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
      "users_id": 2,
      "hospital_id": "EHR-1",
      "name": "saim",
      "email": "saim0067@gmail.com",
      "password": "1234",
      "specialization": null,
      "date_join": "2026-03-05T23:27:55.547000",
      "about": null,
      "phone_no": null
    }
    ```

    **Request Schema (`schema.Login`):**
    - `email` (EmailStr)
    - `password` (str)
    - `hospital_id` (str)

    **Error Responses:**
    - `404 Not Found`: Email is not registered in the system
    - `404 Not Found`: Hospital ID does not exist in the system
    - `404 Not Found`: Password does not match the registered email
    - `400 Bad Request`: Unexpected database or server error
    """
    logger.info(f"Login attempt for email: {doctor.email}")

    if db.get(model.Hospital, doctor.hospital_id) is None:
        logger.warning(f"Signup failed - hospital not found with ID: {doctor.hospital_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="hospital id not valid")

    try:
        is_valid_doc = db.query(model.Users).filter(model.Users.email == doctor.email, model.Users.hospital_id == doctor.hospital_id, model.Users.roll == 1).first()
    except Exception as e:
        logger.error(f"Database error during login for email {doctor.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

    if is_valid_doc is None:
        logger.warning(f"Login failed - email not found for hospital ID: {doctor.hospital_id}, email: {doctor.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid for this hospital")

    if not is_valid_doc:
        logger.warning(f"Login failed - email not found: {doctor.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
    
    if is_valid_doc.password != doctor.password:
        logger.warning(f"Login failed - invalid password for email: {doctor.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")
    
    is_valid_doc.hospital_id = doctor.hospital_id  # Ensure hospital_id is set in the response
    
    logger.info(f"Successful login for user ID: {is_valid_doc.users_id}, email: {doctor.email}")
    return is_valid_doc

@router.get("/get-all-doctors/", status_code=status.HTTP_200_OK, response_model=list[schema.DoctorResponse])
def get_all_doctors(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all registered users (doctors and admins).

    **Response (200 OK):**
    Returns a JSON array of all user records from the database. Each item contains:
    - `users_id` (int): Unique identifier for the user
    - `hospital_id` (str): Hospital ID associated with the user, or null for admins
    - `name` (str, nullable): User's full name
    - `email` (str): User's registered email address
    - `password` (str): User's password
    - `specialization` (str, nullable): Medical specialization or role description
    - `date_join` (datetime): Timestamp when user registered in system
    - `about` (str, nullable): Brief bio or description about the user
    - `phone_no` (str, nullable): User's phone number

    **Example Response:**
    ```json
    [
      {
        "users_id": 2,
        "hospital_id": "EHR-1",
        "name": "saim",
        "email": "saim0067@gmail.com",
        "password": "1234",
        "specialization": null,
        "date_join": "2026-03-05T23:27:55.547000",
        "about": null,
        "phone_no": null
      }
    ]
    ```

    **Error Responses:**
    - `400 Bad Request`: Unexpected database or server error.
    """
    try:
        logger.info("Fetching all users from database")
        users = db.query(model.Users).all()
        logger.info(f"Retrieved {len(users)} users from database")
        return users
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving all users: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
    

@router.get("/get-doctor/{doc_id}", status_code=status.HTTP_200_OK, response_model=schema.DoctorResponse)
@limiter.limit("40/minute")
def get_doctor(doc_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve a user's record by their ID.

    **Path Parameters:**
    - `doc_id` (int, required): The unique database ID of the user (users_id).

    **Response (200 OK):**
    Returns the full user object with the following fields:
    - `users_id` (int): Unique identifier for the user
    - `hospital_id` (str): Hospital ID associated with the user
    - `name` (str, nullable): User's full name
    - `email` (str): User's registered email address
    - `password` (str): User's password
    - `specialization` (str, nullable): Medical specialization or role description
    - `date_join` (datetime): Timestamp when user registered in system
    - `about` (str, nullable): Brief bio or description about the user
    - `phone_no` (str, nullable): User's phone number

    **Example Response:**
    ```json
    {
      "users_id": 2,
      "hospital_id": "EHR-1",
      "name": "saim",
      "email": "saim0067@gmail.com",
      "password": "1234",
      "specialization": null,
      "date_join": "2026-03-05T23:27:55.547000",
      "about": null,
      "phone_no": null
    }
    ```

    **Error Responses:**
    - `404 Not Found`: No user exists with the given `doc_id` (returns None)
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        logger.info(f"Fetching doctor with ID: {doc_id}")
        doctor = db.get(model.Users, doc_id)
        if doctor is None:
            logger.warning(f"Doctor not found with ID: {doc_id}")
        else:
            logger.info(f"Retrieved doctor with ID: {doc_id}, email: {doctor.email}")
        return doctor
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving doctor with ID {doc_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        
@router.post("/add-hospital", status_code=status.HTTP_201_CREATED)
def add_hospital(name: str, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Create a new hospital in the system.

    **Input:**

    - `name` (str)

    **Response (201 Created):**
    Returns a JSON confirmation message with the newly created hospital ID:
    ```json
    {
      "message": "Hospital added successfully",
      "hospital_id": "EHR-1"
    }
    ```

    **Error Responses:**
    - `400 Bad Request`: Database error or validation error
    """
    try:
        logger.info(f"Adding new hospital with name: {name}")
        last_hospital = db.query(model.Hospital).order_by(desc(model.Hospital.hospital_id)).first()
        if last_hospital is None:
            new_id = "EHR-1"
        else:
            last_id_num = int(last_hospital.hospital_id.split("-")[1])
            new_id = f"EHR-{last_id_num + 1}"
            
        new_hospital = model.Hospital(name=name, hospital_id=new_id)
        db.add(new_hospital)
        db.commit()
        db.refresh(new_hospital)
        logger.info(f"Hospital added successfully with ID: {new_hospital.hospital_id}, name: {name}")
        return JSONResponse(content={"message": "Hospital added successfully", "hospital_id": new_hospital.hospital_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding hospital with name {name}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        
@router.get("/all-hospitals", status_code=status.HTTP_200_OK)
def get_all_hospitals(request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Retrieve a list of all hospitals in the system.

    **Response (200 OK):**
    Returns a **List** with json like this:
    ```json
    {
      "hospital_id": "EHR-1",
      "name": "Shifa International"
    }
    ```

    **Error Responses:**
    - `400 Bad Request`: Database error or validation error
    """
    try:
       return db.query(model.Hospital).all()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error while retrieving all hospitals: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.put("/change-doctor/{doc_id}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
def alter_doctor_info(doc_id: int, doctor: schema.DoctorUpdate, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Update user information (phone number, specialization, and about).

    **Path Parameters:**
    - `doc_id` (int, required): The unique ID of the user to update (users_id).

    **Request Body:**
    - `phone_no` (str, required): User's phone number.
    - `specialization` (str, required): User's medical specialization or role description.
    - `about` (str, required): User's bio or description.

    **Response (202 Accepted):**
    Returns a JSON confirmation message:
    ```json
    {
      "message": "Doctor updated successfully"
    }
    ```

    **Request Schema (`schema.DoctorUpdate`):**
    - `phone_no` (str)
    - `specialization` (str)
    - `about` (str)

    **Error Responses:**
    - `404 Not Found`: No user exists with the given `doc_id`
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        logger.info(f"Updating information for doctor ID: {doc_id}")
        doc = db.query(model.Users).filter(model.Users.users_id == doc_id).first()

        if not doc:
            logger.warning(f"Doctor not found for update with ID: {doc_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="doctor id not valid")
        
        doc.phone_no = doctor.phone_no
        doc.about = doctor.about
        doc.specialization = doctor.specialization

        db.add(doc)
        db.commit()
        logger.info(f"Doctor successfully updated for doctor ID: {doc_id}")

        return {'message': "Doctor updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating doctor with ID {doc_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
