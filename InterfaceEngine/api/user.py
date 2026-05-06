"""
User Authentication API Router

This module provides user authentication endpoints including sign-up and login functionality.
Rate limiting is applied to all endpoints to prevent abuse.

Endpoints:
    - POST /sign-up: Create a new user account
    - POST /login: Authenticate a user and return user ID
"""

from fastapi import APIRouter, status, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

import models
from database import get_db
from rate_limiting import limiter

router = APIRouter(tags=["User"])


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
def add_user(user: User, db: Session = Depends(get_db)):
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
def login_user(user: User, db: Session = Depends(get_db)):
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