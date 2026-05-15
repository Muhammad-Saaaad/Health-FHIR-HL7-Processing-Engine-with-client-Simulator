from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import auth_schema as schema
from rate_limiting import limiter

router = APIRouter(tags=["Authentication"])
from .logging_config import get_logger

logger = get_logger('Payer.api.auth', logfile=r'logs\payer_api.log')

@router.post("/signup-admin", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_admin(admin: schema.Admin, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Register a new admin in the Payer system.

    **Request Body:**
    - `email` (EmailStr, required): Admin's email address.
    - `password` (str, required): Password for authentication.

    **Response (201 Created):**
    Returns a JSON confirmation message:
    ```json
    {
      "message": "Admin account created successfully"
    }
    ```

    **Constraints:**
    - Role is automatically set to 2 (Admin).
    - Admin is created without an insurance_id.

    **Error Responses:**
    - `400 Bad Request`: Email already exists or database error.
    """
    logger.info(f"admin signup attempt: email={admin.email}")

    if db.query(models.SystemUser).filter(models.SystemUser.email == admin.email).first():
        logger.warning(f"admin signup failed - email already registered: {admin.email}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    try:
        new_admin = models.SystemUser(
            user_name="Admin",
            email=admin.email,
            password=admin.password,
            roll=2
        )
        db.add(new_admin)
        db.commit()
        logger.info(f"admin signup successful: user_id={new_admin.user_id} email={new_admin.email}")
        return JSONResponse(content={"message": "Admin account created successfully"})
    except Exception as e:
        db.rollback()
        logger.exception(f"admin signup failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login-admin", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def login_admin(admin: schema.Admin, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate an admin and log in to the Payer system.

    **Request Body:**
    - `email` (EmailStr, required): Admin's registered email address.
    - `password` (str, required): Admin's password.

    **Response (200 OK):**
    Returns the authenticated admin user object.

    **Error Responses:**
    - `404 Not Found`: Email is not registered as an admin.
    - `404 Not Found`: Password does not match.
    - `400 Bad Request`: Unexpected database error.
    """
    logger.info(f"admin login attempt: email={admin.email}")

    try:
        user = db.query(models.SystemUser).filter(
            models.SystemUser.email == admin.email,
            models.SystemUser.roll == 2
        ).first()
    except Exception as e:
        logger.exception(f"admin login database error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not user:
        logger.warning(f"admin login failed - invalid email: {admin.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid Email")

    if user.password != admin.password:
        logger.warning(f"admin login failed - invalid password for email: {admin.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid Password")

    logger.info(f"admin login successful: user_id={user.user_id} email={admin.email}")
    return user


@router.post("/signup", response_model=schema.SystemUserDisplay, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # Limit to 10 requests per minute per IP
def signup_user(data: schema.SystemUserCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Create a new user account (signup).
    
    **Request Body:**
    - `user_name` (str, required): Username for the account. Must be unique.
    - `email` (str, required): Email address. Must be a valid email format and unique.
    - `password` (str, required): Password for authentication. Minimum 6 characters recommended.
    - `insurance_id` (str, required): ID of the insurance company the user is associated with.
    
    **Response:**
    Returns `schema.SystemUserDisplay` with:
    - `user_id`: Unique identifier
    - `insurance_id`: Associated insurance ID, if any
    - `user_name`: The username
    - `email`: The email address
    - `roll`: Role identifier (1 for normal user)
    
    **Error Responses:**
    - 400 Bad Request: Email already registered
    - 422 Unprocessable Entity: Invalid email format or missing required fields
    """
    logger.info(f"signup attempt: email={data.email} user_name={data.user_name}")
    existing_user = db.query(models.SystemUser).filter(models.SystemUser.email == data.email, models.SystemUser.insurance_id == data.insurance_id).first()
    if existing_user:
        logger.warning(f"signup failed - email already registered in this insurance company: {data.email}")
        raise HTTPException(status_code=400, detail="Email already registered")


    new_user = models.SystemUser(
        user_name=data.user_name,
        email=data.email,
        password=data.password,
        insurance_id=data.insurance_id,
        roll=1
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info(f"signup successful: user_id={new_user.user_id} email={new_user.email}")
    return new_user

@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")  # Limit to 10 login attempts per minute per IP
def login_user(data: schema.LoginRequest,request: Request, response: Response,  db: Session = Depends(get_db)):
    """
    Authenticate user and login.
    
    **Request Body:**
    - `email` (str, required): User's email address for authentication
    - `password` (str, required): User's password for authentication
    - `insurance_id` (str, required): ID of the insurance company the user is associated with
    
    **Response:**
    Returns JSON object with:
    - `message`: "Login Successful"
    - `user_id`: The user's unique identifier
    - `user_name`: The username
    - `insurance_id` (str, required): ID of the insurance company the user is associated with
    
    **Error Responses:**
    - 404 Not Found: Invalid Email - Email not registered in system
    - 404 Not Found: Invalid Password - Password does not match the registered email
    - 422 Unprocessable Entity: Invalid email format or missing fields
    """
    logger.info(f"login attempt: email={data.email}")
    user = db.query(models.SystemUser).filter(
        models.SystemUser.email == data.email,
        models.SystemUser.roll == 1,
        models.SystemUser.insurance_id == data.insurance_id
    ).first()
    if not user:
        logger.warning(f"login failed - invalid email: {data.email}")
        raise HTTPException(status_code=404, detail="Invalid Email")
    
    if user.password != data.password:
        logger.warning(f"login failed - invalid password for email: {data.email}")
        raise HTTPException(status_code=404, detail="Invalid Password")

    logger.info(f"login successful: user_id={user.user_id} email={data.email}")
    return {
        "message": "Login Successful",
        "user_id": user.user_id,
        "user_name": user.user_name,
        "insurance_id": user.insurance_id
    }


@router.post("/add-insurance", status_code=status.HTTP_201_CREATED)
def add_insurance(name: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Create a new insurance company in the Payer system.

    **Input:**
    - `name` (str): Insurance company name.

    **Response (201 Created):**
    Returns a JSON confirmation message with the generated insurance ID:
    ```json
    {
      "message": "Insurance added successfully",
      "insurance_id": "PAYER-1"
    }
    ```

    **Error Responses:**
    - `400 Bad Request`: Database error or validation error.
    """
    try:
        logger.info(f"adding insurance: name={name}")

        if db.query(models.Insurance).filter(models.Insurance.name == name).first():
            logger.warning(f"add insurance failed - name already exists: {name}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insurance already exists")

        last_insurance = db.query(models.Insurance).order_by(desc(models.Insurance.insurance_id)).first()
        if last_insurance is None:
            new_id = "PAYER-1"
        else:
            last_id_num = int(last_insurance.insurance_id.split("-")[1])
            new_id = f"PAYER-{last_id_num + 1}"

        new_insurance = models.Insurance(insurance_id=new_id, name=name)
        db.add(new_insurance)
        db.commit()
        db.refresh(new_insurance)
        logger.info(f"insurance added successfully: insurance_id={new_insurance.insurance_id} name={name}")
        return JSONResponse(content={"message": "Insurance added successfully", "insurance_id": new_insurance.insurance_id})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"add insurance failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/all-insurances", status_code=status.HTTP_200_OK)
def get_all_insurances(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all insurance companies in the Payer system.

    **Response (200 OK):**
    Returns a list like:
    ```json
    [
      {
        "insurance_id": "PAYER-1",
        "name": "ABC Insurance"
      }
    ]
    ```

    **Error Responses:**
    - `400 Bad Request`: Database error.
    """
    try:
        return db.query(models.Insurance).all()
    except Exception as e:
        logger.exception(f"get all insurances failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
