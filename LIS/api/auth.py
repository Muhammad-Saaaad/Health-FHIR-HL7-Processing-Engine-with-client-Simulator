import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db
import model
from schemas.auth_schema import SignUp, Login, UserOut, SignUpAdmin, LoginAdmin
from rate_limiting import limiter

router = APIRouter(tags=["Authentication"])

logger = logging.getLogger("lis_authentication")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/auth.log", maxBytes=1000000, backupCount=2)
handler.setFormatter(formatter)
logger.addHandler(handler)


@router.post("/signup-admin", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_admin(admin: SignUpAdmin, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Register a new admin in the LIS system.

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

    **Request Schema (`SignUpAdmin`):**
    - `email` (EmailStr)
    - `password` (str)

    **Constraints:**
    - Role is automatically set to 2 (Admin).
    - Admin is created without a lab_id (lab_id = NULL).
    - Admin username is optional because `user_name` is nullable in the LIS user model.

    **Error Responses:**
    - `400 Bad Request`: Database error or validation error
    """
    try:
        logger.info(f"Admin signup request received for email: {admin.email}")
        
        if db.query(model.User).filter(model.User.email == admin.email).first():
            logger.warning(f"Admin signup failed - email already exists: {admin.email}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email already exists")
        
        new_admin = model.User(
            name="Admin",
            email = admin.email,
            password = admin.password,
            roll=2
        )
        db.add(new_admin)
        db.commit()
        logger.info(f"Admin account created successfully with ID: {new_admin.user_id}, email: {admin.email}")
        return JSONResponse(content={"message": "Admin account created successfully"})
    except Exception as e:
        logger.error(f"Error creating admin account for email {admin.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.post("/login-admin", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def login_admin(admin: LoginAdmin, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Authenticate an admin and log in to the LIS system.

    **Request Body:**
    - `email` (EmailStr, required): Admin's registered email address.
    - `password` (str, required): Admin's password.

    **Response (200 OK):**
    Returns the authenticated admin user object with the following fields:
    - `user_id` (int): Unique identifier for the admin
    - `lab_id` (str, nullable): Associated lab ID (typically NULL for admins)
    - `user_name` (str, nullable): Admin username, if provided
    - `email` (str): Admin's registered email address
    - `password` (str): Admin's password
    - `roll` (int): Role identifier (2 for Admin)
    - `created_at` (datetime): Timestamp when admin was registered

    **Request Schema (`LoginAdmin`):**
    - `email` (EmailStr)
    - `password` (str)

    **Error Responses:**
    - `404 Not Found`: Email is not registered in the system
    - `404 Not Found`: Password does not match the registered email
    - `400 Bad Request`: Unexpected database or server error
    """
    
    try:
        is_valid_user = db.query(model.User).filter(model.User.email == admin.email, model.User.roll == 2).first()
    except Exception as e:
        logger.error(f"Database error during login for email {admin.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        
    if not is_valid_user:
        logger.warning(f"Login failed - email not found: {admin.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
    
    if is_valid_user.password != admin.password:
        logger.warning(f"Login failed - invalid password for email: {admin.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")

    logger.info(f"Successful login for user ID: {is_valid_user.user_id}, email: {admin.email}")
    return is_valid_user


@router.post("/SignUp", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")  # Limit to 5 sign-up attempts per minute per IP
def SignUp(user: SignUp,request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Register a new lab technician/user in the LIS system.

    **Request Body:**
    - `user_name` (str, required): Desired username for the new account.
    - `email` (str, required): User's email address. Must be unique within the same lab.
    - `password` (str, required): Password for authentication.
    - `lab_id` (str, required): The ID of the lab to which the user belongs.

    **Response (201 Created):**
    Returns the newly created user object including:
    - `user_id`: Auto-generated unique user identifier
    - `user_name`: The registered username
    - `email`: The registered email address
    - `lab_id`: The associated lab ID
    - `roll`: Role identifier (1 for lab technician/user)

    **Constraints:**
    - The specified lab ID must exist.
    - The same email cannot be reused within the same lab.

    **Error Responses:**
    - `404 Not Found`: Lab ID does not exist
    - `400 Bad Request`: Email already exists for this lab
    """
    if db.get(model.Lab, user.lab_id) is None:
        logger.warning(f"Signup failed - lab not found with ID: {user.lab_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lab id not valid")
        
    if db.query(model.User).filter(model.User.email == user.email, model.User.lab_id == user.lab_id).first():
        logger.warning(f"Signup failed - email already exists for lab ID: {user.lab_id}, email: {user.email}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email already exists for this lab")
    
    db_user = model.User(
        user_name = user.user_name,
        email = user.email,
        password = user.password,
        lab_id = user.lab_id,
        roll=1
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/Login", status_code=status.HTTP_200_OK, response_model=UserOut)
@limiter.limit("10/minute")  # Limit to 10 login attempts per minute per IP
def login(data: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate a lab technician/user and log in to the LIS system.

    **Request Body:**
    - `email` (str, required): The user's registered email address.
    - `password` (str, required): The user's password.
    - `lab_id` (str, required): The ID of the lab to which the user belongs.

    **Response (200 OK):**
    Returns the user object on successful login:
    - `user_id`: Auto-generated unique user identifier
    - `user_name`: The logged-in user's username
    - `email`: The logged-in user's email address
    - `lab_id`: The associated lab ID
    - `roll`: Role identifier (1 for lab technician/user)

    **Error Responses:**
    - `404 Not Found`: Lab ID does not exist
    - `404 Not Found`: Email is not registered for the provided lab
    - `404 Not Found`: Password does not match the registered email
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        logger.info(f"Login attempt for email: {data.email}")

        if db.get(model.Lab, data.lab_id) is None:
            logger.warning(f"Signup failed - lab not found with ID: {data.lab_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lab id not valid")

        is_valid_user = db.query(model.User).filter(model.User.email == data.email, model.User.lab_id == data.lab_id, model.User.roll == 1).first()
        if is_valid_user is None:
            logger.warning(f"Login failed - email not found for lab ID: {data.lab_id}, email: {data.email}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid for this lab")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error during login for email {data.email}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        
    if not is_valid_user:
        logger.warning(f"Login failed - email not found: {data.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
    
    if is_valid_user.password != data.password:
        logger.warning(f"Login failed - invalid password for email: {data.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")
    
    is_valid_user.lab_id = data.lab_id  # Ensure lab_id is set in the response
    
    logger.info(f"Successful login for user ID: {is_valid_user.user_id}, email: {data.email}")
    return is_valid_user

@router.post("/add-lab", status_code=status.HTTP_201_CREATED)
def add_lab(name: str, request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Create a new lab in the system.

    **Input:**

    - `name` (str)

    **Response (201 Created):**
    Returns a JSON confirmation message with the newly created lab ID:
    ```json
    {
      "message": "Lab added successfully",
      "lab_id": "LIS-1"
    }
    ```

    **Error Responses:**
    - `400 Bad Request`: Database error or validation error
    """
    try:
        logger.info(f"Adding new lab with name: {name}")
        last_lab = db.query(model.Lab).order_by(desc(model.Lab.lab_id)).first()
        if last_lab is None:
            new_id = "LIS-1"
        else:
            last_id_num = int(last_lab.lab_id.split("-")[1])
            new_id = f"LIS-{last_id_num + 1}"
            
        new_lab = model.Lab(name=name, lab_id=new_id)
        db.add(new_lab)
        db.commit()
        db.refresh(new_lab)
        logger.info(f"Lab added successfully with ID: {new_lab.lab_id}, name: {name}")
        return JSONResponse(content={"message": "Lab added successfully", "lab_id": new_lab.lab_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding lab with name {name}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        
@router.get("/all-labs", status_code=status.HTTP_200_OK)
def get_all_labs(request: Request, response: Response, db :Session = Depends(get_db)):
    """
    Retrieve a list of all labs in the system.

    **Response (200 OK):**
    Returns a **List** with json like this:
    ```json
    {
      "lab_id": "LIS-1",
      "name": "Shifa Lab"
    }
    ```

    **Error Responses:**
    - `400 Bad Request`: Database error or validation error
    """
    try:
       return db.query(model.Lab).all()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error while retrieving all labs: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

