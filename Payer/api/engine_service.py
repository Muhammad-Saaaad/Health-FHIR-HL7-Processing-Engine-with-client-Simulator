from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter(tags=["Engine"])

@router.post("/register/patient/", status_code=status.HTTP_200_OK)
async def register(req: dict, db: Session = Depends(get_db)):
    """
    Internal engine endpoint to register a patient synced from an external FHIR source.

    This endpoint is intended to be called by the InterfaceEngine (not directly from the front-end).
    It accepts a raw JSON payload containing patient information and persists it to the Payer database.

    **Request Body (raw JSON):**
    - `mpi` (str/int, required): Master Patient Index - unique identifier from the FHIR system.
    - `name` (str, required): Patient's full name.
    - `gender` (str, required): Patient's gender (e.g., "Male", "Female").
    - `date_of_birth` (str, required): Patient's date of birth in YYYY-MM-DD format.

    **Response (200 OK):**
    Returns a confirmation message:
    - `message`: "Patient Successfully Added"

    **Note:**
    - This is an internal service-to-service endpoint. The request body is not validated
      by a Pydantic schema; missing fields will raise an unhandled exception.

    **Error Responses:**
    - `400 Bad Request`: Any exception during patient creation (e.g., missing fields, DB error)
    """
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