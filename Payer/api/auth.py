from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import auth_schema as schema

router = APIRouter(tags=["Authentication"])

@router.post("/signup", response_model=schema.SystemUserDisplay, status_code=status.HTTP_201_CREATED, tags=["Users"])
def signup_user(request: schema.SystemUserCreate, db: Session = Depends(get_db)):

    existing_user = db.query(models.SystemUser).filter(models.SystemUser.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")


    new_user = models.SystemUser(
        user_name=request.user_name,
        email=request.email,
        password=request.password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", status_code=status.HTTP_200_OK, tags=["Users"])
def login_user(request: schema.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.SystemUser).filter(models.SystemUser.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid Email")
    
    if user.password != request.password:
        raise HTTPException(status_code=404, detail="Invalid Password")

    return {
        "message": "Login Successful",
        "user_id": user.user_id,
        "user_name": user.user_name
    }
