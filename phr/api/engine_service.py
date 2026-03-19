import logging
from logging.handlers import RotatingFileHandler
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from fhir_validation import fhir_extract_paths, get_fhir_value_by_path

from database import get_db
import model

router = APIRouter(tags=["Engine-Service"])

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("get_data")
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

if not logger.handlers:
    rotating_file_handler = RotatingFileHandler(
        r"./logs/recieve_data.log",
        maxBytes=20000, # 20KB
        backupCount=1
    )
    rotating_file_handler.setFormatter(formater)
    logger.addHandler(rotating_file_handler)


@router.post("/add/patient", status_code=status.HTTP_200_OK)
async def add_patient(req: Request, db: Session = Depends(get_db)):
    
    try:
        json_data = await req.json()

        resource_type = json_data['resourceType']
        db_data = {}
        if resource_type != "Bundle":

            paths = fhir_extract_paths(json_data)
            for path in paths:

                value = get_fhir_value_by_path(json_data, path)
                db_data[path] = value
                # print("path => ",path)
                # print("value => ",value)
        else: # if resource is Bundle

            for entry in json_data["entry"]:

                resource_type = entry['resource']['resourceType']
                paths = fhir_extract_paths(entry['resource'])
                for path in paths:

                    value = get_fhir_value_by_path(json_data, path)
                    db_data[path] = value
        
        print(db_data)
        return {"message": db_data}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

"""
Sample Message:

{
  "resourceType": "Patient",
  "identifier": [
        { "type": { "coding": [{ "code": "MR" }]}, "value": "23" },
        { "type": { "coding": [{ "code": "NI" }]}, "value": "37201-23123123"}
    ],
  "name": [{"text": "Muhammad Saad"}],
  "gender": "male",
  "birthDate": "2004-10-06",
  "address": [{ "text": "123 street, city, country" }],
  "telecom" : [{
      "value" : "+33 (237) 998327"
    }]
}

"""