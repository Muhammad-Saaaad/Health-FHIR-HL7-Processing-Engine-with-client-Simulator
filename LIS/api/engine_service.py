from fastapi import APIRouter, status, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from database import get_db
import model

router = APIRouter(tags=['Engine'])

@router.post("/hl7/add-patient", status_code=status.HTTP_200_OK)
async def add_patient(req: Request, db: Session = Depends(get_db)):
    try:
        data = await req.json()
        # patient = model.Patient(
        #     mpi = data['mpi'],
        #     fname = data['name'],
        #     lname = data['name'],
        #     dob = data['date_of_birth'],
        #     gender = data['gender']
        # )

        # db.add(patient)
        # db.commit()
        # db.refresh(patient)
        print(data)

        return {"message": "Patient Added sucessfully"}

    except Exception as exp:
        raise HTTPException(str(exp))