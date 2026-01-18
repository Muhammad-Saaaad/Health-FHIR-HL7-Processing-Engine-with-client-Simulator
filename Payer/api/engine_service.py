from fastapi import APIRouter, status, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter(tags=["Engine"])

@router.post("/register/patient/", status_code=status.HTTP_200_OK)
async def register(req: Request, db: Session= Depends(get_db)):
    try:
        data = await req.json()
        patient = models.Patient(
            mpi = data['mpi'],
            name = data['name'],
            gender = data['gender'],
            date_of_birth = data['date_of_birth']
        )

        db.add(patient)
        db.commit()

        return {"message": "Patient Successfully Added"}
    except Exception as exp:
        raise HTTPException(str(exp), status_code=status.HTTP_400_BAD_REQUEST)