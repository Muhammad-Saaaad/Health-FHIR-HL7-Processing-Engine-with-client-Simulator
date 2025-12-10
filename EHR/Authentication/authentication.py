from datetime import datetime, timezone

from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import session

import model
from database import get_db
import schemas

router = APIRouter(tags=['Authentication'])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: schemas.SignUp, db :session = Depends(get_db)):
    new_doctor = model.Doctor(
        name = doctor.name,
        email = doctor.email,
        password = doctor.password,
        date_join = datetime.now(timezone.utc) # utc = Cordinated universal time
    )
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    return JSONResponse(content={"message": "data inserted sucessfully"})

@router.post("/login",status_code=status.HTTP_200_OK)
def login_doctor(doctor: schemas.Login, db :session = Depends(get_db)):

    is_valid_doc = db.query(model.Doctor).filter(
        model.Doctor.email == doctor.email).first()
    
    if not is_valid_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
    
    if is_valid_doc.password != doctor.password:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")
    
    return {"message": "login sucessfully"}
