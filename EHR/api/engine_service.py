import asyncio
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from fhir_validation import get_fhir_value_by_path, fhir_extract_paths
from database import get_db
import model

router = APIRouter(tags=["Engine"])

logger = logging.getLogger("engine_service_logger")
logger.setLevel(logging.INFO)
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")
if not logger.handlers:
    rotating_file_handler = RotatingFileHandler(
        r"logs\engine_service.log",
        maxBytes=20000, # 20KB
        backupCount=1
    )
    rotating_file_handler.setFormatter(formater)
    logger.addHandler(rotating_file_handler)

async def send_to_engine(data: dict, url: str):
    """
    Send a FHIR data to the InterfaceEngine for routing to downstream services.

    Returns:
        str: "sucessfull" if the engine responds with HTTP 200.

    Raises:
        Exception: If the engine returns a non-200 status (e.g., 502 on partial downstream failure),
                   raises an exception with the engine's error detail so the caller can rollback.
    """
    try:
        logger.info(f"Sending data to engine: {data}")
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, timeout=7)
            if response.status_code == 200:
                logger.info(f"Successfully sent data to engine with url {url}")
                return "sucessfull"
            raise Exception(response.json().get("detail", f"Engine returned {response.status_code}"))

    except Exception as exp:
        logger.error(f"Failed to send data to engine: {str(exp)}")
        raise

@router.post("/fhir/claim-response")
async def submit_claim_from_engine(req: Request, db: Session = Depends(get_db)):
    """
    Ingest patient FHIR payload from InterfaceEngine and store in PHR database.

    **Response (200 OK):**
    Returns JSON object:
    - `message` (dict): extracted FHIR path-value map used for DB insertion.

    **Error Responses:**
    - `400 Bad Request`: Payload parsing, mapping, or database error.
    """
    try:
        json_data = await req.json()

        logger.info(f"Recieved FHIR Data: {json_data}")

        resource_type = json_data['resourceType']
        db_data = {}
        if resource_type != "Bundle":

            paths = fhir_extract_paths(json_data)
            for path in paths:

                value = get_fhir_value_by_path(json_data, path)
                db_data[path] = value
        else: # if resource is Bundle
            for entry in json_data["entry"]:

                resource_type = entry['resource']['resourceType']
                paths = fhir_extract_paths(entry['resource'])
                for path in paths:

                    value = get_fhir_value_by_path(json_data, path)
                    db_data[path] = value

        mpi = str(db_data.get("patient.reference").split("/")[-1]).strip() # MPI
        vid = str(db_data.get("request.reference").split("/")[-1]).strip() # vid
        claim_status = str(db_data.get("status")).strip()
        logger.info(f"Extracted data for DB: MPI={mpi}, VID={vid}, Status={claim_status}")

        visit_note = db.query(model.VisitingNotes).filter(model.VisitingNotes.mpi == mpi, model.VisitingNotes.note_id == vid).first()
        if visit_note:
            bill = db.get(model.Bill, visit_note.bill_id)
            bill.bill_status = "Paid" if str(claim_status).lower() == "approved" else "Denied"
            bill.bill_date = datetime.now()
            db.add(bill)
            db.commit()
            logger.info(f"Updated bill status to {bill.bill_status} for MPI={mpi}, VID={vid}")

            fhir_msg = {
                "resourceType": "ClaimResponse",
                "id": str(uuid4()), 
                "status": bill.bill_status,
                "type": { "coding": [{"code": "professional"}] },
                "use": "claim",
                "patient": {
                    "reference": "patient/"+str(mpi) 
                },
                "request": {
                    "reference": "Encounter/"+str(vid)
                },
                "created": bill.bill_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "insurer": {
                    "display": "Jubilee Insurance"
                },
                "outcome": "complete"
            }
            logger.info(f"Prepared FHIR ClaimResponse to send to engine: {fhir_msg}")

            asyncio.create_task(send_to_engine(data=fhir_msg, url="http://127.0.0.1:9000/fhir/send-response-claim"))
            logger.info(f"Successfully sent claim response to engine for MPI={mpi}, VID={vid}")       

            return {"message": f"Bill status updated to {bill.bill_status} for MPI={mpi}, VID={vid}"}
        else:
            logger.error(f"No visit note found for MPI={mpi}, VID={vid}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visit note found for MPI={mpi}, VID={vid}")


    except Exception as e:
        logger.error(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
