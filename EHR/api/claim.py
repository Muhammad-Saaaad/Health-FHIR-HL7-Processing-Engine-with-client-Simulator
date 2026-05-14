import asyncio
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from uuid import uuid4

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.orm.attributes import flag_modified
# from sqlalchemy.ext.asyncio import AsyncSession

from .engine_service import send_to_engine
from database import get_db
import model
from rate_limiting import limiter
from schemas import claim_schema as schema

router = APIRouter(tags=['claim'])

logger = logging.getLogger("ehr_claims")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/claims.log", maxBytes=1000000, backupCount=2)
handler.setFormatter(formatter)
logger.addHandler(handler)

@router.post("/submit-claims")
@limiter.limit("30/minute")
async def submit_claim(claim_data: schema.ClaimSubmission, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Submit an insurance claim for an existing visit note.

    **Request Body (`schema.ClaimSubmission`):**
    - `vid` (int, required): Visit note ID.
    - `mpi` (int, required): Patient Master Patient Index.
    - `service_included` (bool, required): Whether consultation/service charges are included.
    - `lab_included` (bool, required): Whether lab charges are included.
    - `total_fee` (float, required): Total amount submitted in the claim.

    **Response (200 OK):**
    Returns one of:
    ```json
    { "detail": "Claim submitted successfully." }
    ```
    ```json
    { "message": "data added to config due to hold flag" }
    ```

    **Side Effects:**
    - Builds a FHIR Claim resource and sends or queues it for the InterfaceEngine.
    - Sets the linked bill status to `"In Process"`.

    **Error Responses:**
    - `404 Not Found`: Visit note, patient, or bill was not found.
    - `400 Bad Request`: A claim is already in process for this visit note.
    - `500 Internal Server Error`: Unexpected claim submission failure.
    """
    visit_note = db.get(model.VisitingNotes, claim_data.vid)
    if visit_note is None:
        logger.warning(f"Claim submission attempted for MPI {claim_data.mpi} and VID {claim_data.vid} but no visit note found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visiting note not found.")
    
    is_patient = db.get(model.Patient, claim_data.mpi)
    if is_patient is None:
        logger.warning(f"Claim submission attempted for MPI {claim_data.mpi} and VID {claim_data.vid} but no patient found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    
    bill = db.query(model.Bill).filter(model.Bill.bill_id == visit_note.bill_id).first()
    if bill is None:
        logger.warning(f"Claim submission attempted for MPI {claim_data.mpi} and VID {claim_data.vid} but no bill found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found for the visit note.")
    
    if bill.bill_status == "In Process":
        logger.warning(f"Claim submission attempted for MPI {claim_data.mpi} and VID {claim_data.vid} but a claim is already in process.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Claim is already in process for this visit note.")
    
    # lab_tests = db.query(model.LabReport).filter(model.LabReport.visit_id == claim_data.vid).all() 
    # for test in lab_tests:
    #     if test and test.test_status != "Arrived":
    #         logger.warning(f"Claim submission attempted for MPI {claim_data.mpi} and VID {claim_data.vid} but a lab test is not completed.")
    #         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more lab tests are not completed for this visit note.")

    try:
        now_datetime = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        fhir_msg = {
            "resourceType": "Claim",
            "id": str(uuid4()),
            "status": "active",
            "type": {
                "coding": [
                    {
                        "display": "Service_LabTest" if claim_data.service_included and claim_data.lab_included else "Service_Only"
                    }   
                ]
            },
            "use": "claim",
            "patient": {
                "reference": "patient/"+str(is_patient.nic)
            },
            "provider": {
                "reference":  "Encounter/"+str(claim_data.vid)
            },
            "created": now_datetime,
            "priority": {
                "coding": [
                    {
                        "code": "normal"
                    }
                ]
            },
            "insurance": [
                {
                    "sequence": 1,
                    "focal": True,
                    "coverage": {
                        "display": "Payer Health Insurance"
                    }
                }
            ],
            "total": {
                "value": claim_data.total_fee
            }
        }

        hospital = db.query(model.Hospital).filter(model.Hospital.hospital_id == visit_note.hospital_id).first()
        
        config_data= db.query(model.Config).filter(model.Config.sent_to_engine == False) \
            .order_by(desc(model.Config.config_id)).first()
        
        if config_data and config_data.hold_flag: # if we have to hold the data
            history_hospital = config_data.history.get(hospital.name, {})

            if history_hospital:
                history_hospital["submit-claim"] = history_hospital.get("submit-claim", 0) + 1
            else:
                config_data.history[hospital.name] = history_hospital
                config_data.history[hospital.name]["submit-claim"] = 1
            
            endpoint_already_added = False
            for endpoint in config_data.data:
                if endpoint.get("system_id") == hospital.hospital_id and endpoint.get("/fhir/submit-claim"): # if endpoint exists in config.
                    endpoint["/fhir/submit-claim"].append(fhir_msg)
                    endpoint_already_added = True
                    break
            
            if not endpoint_already_added:
                config_data.data.append(
                    {   
                        "system_id": hospital.hospital_id,
                        "/fhir/submit-claim": [fhir_msg]
                    }
                )

            flag_modified(config_data, "history")
            flag_modified(config_data, "data")
            bill.bill_status = "In Process"
            db.add(bill)
            db.commit()
            logger.info(f"Data added to config for hospital {hospital.name} due to hold flag. Current history: {config_data.history}")
            return {"message": "data added to config due to hold flag"}
        

        asyncio.create_task(send_to_engine(fhir_msg, url="http://127.0.0.1:9000/fhir/submit-claim", system_id=str(hospital.hospital_id)))
        bill.bill_status = "In Process"
        db.add(bill)
        db.commit()
        return {"detail": "Claim submitted successfully."}
        
    except Exception as e:
        logger.error(f"Error submitting claim: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while submitting the claim.")
