from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas import auth_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Authentication'])

@router.post("/signup", status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: schema.SignUp, db :Session = Depends(get_db)):
    try:
        new_doctor = model.Doctor(
            name = doctor.name,
            email = doctor.email,
            password = doctor.password
        )
        db.add(new_doctor)
        # db.flush()

        db.commit()
        db.refresh(new_doctor)
        return JSONResponse(content={"message": "data inserted sucessfully"})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.post("/login",status_code=status.HTTP_200_OK)
def login_doctor(doctor: schema.Login, db :Session = Depends(get_db)):
    try:
        is_valid_doc = db.query(model.Doctor).filter(
            model.Doctor.email == doctor.email).first()
        
        if not is_valid_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="email not valid")
        
        if is_valid_doc.password != doctor.password:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="password not valid")
        
        return {"message": "login sucessfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.get("/get-doctor/{email}/{password}", status_code=status.HTTP_200_OK)
def get_doctor(email: str, password: str, db: Session = Depends(get_db)):
    try:
        doctor = db.query(model.Doctor).filter(
            model.Doctor.email == email , model.Doctor.password == password).first()
        return doctor
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
        

@router.put("/change-phone-no{p_no}/id{doc_id}", status_code=status.HTTP_202_ACCEPTED)
def alter_phone_no(p_no: str , doc_id: int, db :Session = Depends(get_db)):
    try:
        doc = db.query(model.Doctor).filter(model.Doctor.doctor_id == doc_id).first()

        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="doctor id not valid")
        
        doc.phone_no = p_no

        db.commit()
        db.refresh(doc)

        return {'message': "phone no added"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
