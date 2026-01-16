from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.auth_schema import SignUp, Login

router = APIRouter(tags=["Authentication"])

@router.post("/SignUp", status_code=status.HTTP_201_CREATED, tags=["user"])
def SignUp(user: SignUp, db: Session = Depends(get_db)):

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
    user = db.query(model.User).filter(model.User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email not exists")

    if user.password != request.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password not exists")
    
    return {"message": "Login sucessfull"}
