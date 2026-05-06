from fastapi import APIRouter, status, HTTPException, Depends, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from schemas.server import AddUpdateServer, GetServer
import models
import db_logger as db_logging
from database import get_db, session_local
from rate_limiting import limiter

router = APIRouter(tags=["User"])


class User(BaseModel):
    email: EmailStr
    password: str

@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")  # Example: Limit to 5 requests per minute
def add_user(user: User, db: Session = Depends(get_db)):
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
def login_user(user: User, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if existing_user.password != user.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credentials")
    
    return {"message": "Login successful", "user_id": existing_user.user_id}