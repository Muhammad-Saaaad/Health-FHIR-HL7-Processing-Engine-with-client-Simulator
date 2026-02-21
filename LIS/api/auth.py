from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.auth_schema import SignUp, Login

router = APIRouter(tags=["Authentication"])

@router.post("/SignUp", status_code=status.HTTP_201_CREATED, tags=["user"])
def SignUp(user: SignUp, db: Session = Depends(get_db)):
    """
    Register a new lab technician/user in the LIS system.

    **Request Body:**
    - `user_name` (str, required): Desired username for the new account. Must be unique.
    - `email` (str, required): User's email address. Must be unique across all users.
    - `password` (str, required): Password for authentication.

    **Response (201 Created):**
    Returns the newly created user object including:
    - `user_id`: Auto-generated unique user identifier
    - `user_name`: The registered username
    - `email`: The registered email address

    **Constraints:**
    - Email must be unique. Duplicate emails are rejected.

    **Error Responses:**
    - `400 Bad Request`: Email already exists in the system
    """
    if db.query(model.User).filter(model.User.email == user.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email already exists")

    db_user = model.User(
        user_name = user.user_name,
        email = user.email,
        password = user.password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/Login", status_code=status.HTTP_200_OK, tags=["user"])
def login(request: Login, db: Session = Depends(get_db)):
    """
    Authenticate a lab technician/user and log in to the LIS system.

    **Request Body:**
    - `email` (str, required): The user's registered email address.
    - `password` (str, required): The user's password.

    **Response (200 OK):**
    Returns a confirmation message on successful login:
    - `message`: "Login sucessfull"

    **Error Responses:**
    - `400 Bad Request`: Email is not registered in the system
    - `400 Bad Request`: Password does not match the registered email
    """
    user = db.query(model.User).filter(model.User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email not exists")

    if user.password != request.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password not exists")
    
    return {"message": "Login sucessfull"}
