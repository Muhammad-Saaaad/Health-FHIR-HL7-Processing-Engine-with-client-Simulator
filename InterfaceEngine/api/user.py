import json

from fastapi import APIRouter, Response, status, HTTPException, Depends, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from schemas.toggel import UpdateStatus
import models
from database import get_db
from rate_limiting import limiter

router = APIRouter(tags=["User"])

TIME = {
    1: "11:00",
    2: "11:05",
    3: "11:10",
    4: "11:15"
}

class User(BaseModel):
    """
    User authentication schema.
    
    Attributes:
        email (EmailStr): User's email address (must be valid email format)
        password (str): User's password
    """
    email: EmailStr
    password: str

@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")  # Example: Limit to 5 requests per minute
def add_user(user: User, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Create a new user account with email and password.
    
    Args:
        user (User): User object containing email and password
        db (Session): Database session dependency
    
    Returns:
        dict: Success message and newly created user_id
        
    Raises:
        HTTPException(400): If email is already registered
        HTTPException(500): If there's a database error during user creation
        
    Rate Limit: 20 requests per minute
    """
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    
    try:

        new_user = models.User(
            email=user.email,
            password=user.password
        )
        db.add(new_user)
        db.commit()

        return {"message": "User created successfully", "user_id": new_user.user_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/login", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")  # Example: Limit to 5 requests per minute
def login_user(user: User,  request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate a user and return their user ID.
    
    Performs basic authentication by checking email and password against the database.
    
    Args:
        user (User): User object containing email and password for authentication
        db (Session): Database session dependency
    
    Returns:
        dict: Success message and authenticated user_id
        
    Raises:
        HTTPException(404): If user email is not found in the database
        HTTPException(400): If password is incorrect
        
    Rate Limit: 20 requests per minute
    
    Note:
        Consider implementing JWT tokens or session management for production use
        instead of returning user_id directly.
    """
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if existing_user.password != user.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credentials")
    
    return {"message": "Login successful", "user_id": existing_user.user_id}


@router.get("/config-history", status_code=status.HTTP_201_CREATED)
def get_history(db: Session = Depends(get_db)):
    try:
        all_config = db.query(models.Config).all()

        response = []
        for config in all_config:
            response.append(
                {
                    "count": config.count,
                    "label": config.hold_type,
                    "flag": config.hold_flag
                }
            )
        
        return response

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exp))

@router.get("/show-data/{flag}")
def get_hold_msg(flag: int ,db: Session = Depends(get_db)):
    try:
        single_config = db.query(models.Config).filter(models.Config.hold_flag == flag).first()

        if not single_config:
            print("Flag not found")
            return []

        response = []
        hold_type = str(single_config.hold_type.split("-")[1]).strip().upper()
        print(hold_type)
        for single_json in single_config.data:

            for single_data_msg in single_json.get("data"):
                print(type(single_data_msg))
                # print(single_json)   

                if  hold_type in ("EHR", "PHR"):
                    single_data_msg = json.dumps(single_data_msg)

                response.append(
                    {
                        "message": single_data_msg
                    }
                )
        
        return response

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exp))


# post /send-data/{flag}

toggle = True

@router.post("/update-status")
def update_status(data: UpdateStatus):
    global toggle

    print(f"Received status update request: {data.status}")

    toggle = data.status

    print("Updated Toggle:", toggle)

    return {
        "message": "Status updated successfully",
        "status": toggle
    }