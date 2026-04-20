from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import auth_schema as schema
from rate_limiting import limiter

router = APIRouter(tags=["Authentication"])

@router.post("/signup", response_model=schema.SystemUserDisplay, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # Limit to 10 requests per minute per IP
def signup_user(data: schema.SystemUserCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Create a new user account (signup).
    
    **Request Body:**
    - `user_name` (str, required): Username for the account. Must be unique.
    - `email` (str, required): Email address. Must be a valid email format and unique.
    - `password` (str, required): Password for authentication. Minimum 6 characters recommended.
    
    **Response:**
    Returns `schema.SystemUserDisplay` with:
    - `user_id`: Unique identifier
    - `user_name`: The username
    - `email`: The email address
    
    **Error Responses:**
    - 400 Bad Request: Email already registered
    - 422 Unprocessable Entity: Invalid email format or missing required fields
    """
    existing_user = db.query(models.SystemUser).filter(models.SystemUser.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")


    new_user = models.SystemUser(
        user_name=data.user_name,
        email=data.email,
        password=data.password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")  # Limit to 10 login attempts per minute per IP
def login_user(data: schema.LoginRequest,request: Request, response: Response,  db: Session = Depends(get_db)):
    """
    Authenticate user and login.
    
    **Request Body:**
    - `email` (str, required): User's email address for authentication
    - `password` (str, required): User's password for authentication
    
    **Response:**
    Returns JSON object with:
    - `message`: "Login Successful"
    - `user_id`: The user's unique identifier
    - `user_name`: The username
    
    **Error Responses:**
    - 404 Not Found: Invalid Email - Email not registered in system
    - 404 Not Found: Invalid Password - Password does not match the registered email
    - 422 Unprocessable Entity: Invalid email format or missing fields
    """
    user = db.query(models.SystemUser).filter(models.SystemUser.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid Email")
    
    if user.password != data.password:
        raise HTTPException(status_code=404, detail="Invalid Password")

    return {
        "message": "Login Successful",
        "user_id": user.user_id,
        "user_name": user.user_name
    }
