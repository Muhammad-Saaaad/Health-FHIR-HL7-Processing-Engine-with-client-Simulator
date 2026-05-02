from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from uuid import uuid4

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
# from sqlalchemy.ext.asyncio import AsyncSession

from .engine_service import send_claim_to_engine
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
    visit_note = db.get(model.VisitingNotes, claim_data.vid)
    if visit_note is None:
        logger.warning(f"Claim submission attempted for MPI {claim_data.mpi} and VID {claim_data.vid} but no visit note found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visiting note not found.")
    
    if db.get(model.Patient, claim_data.mpi) is None:
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
                "reference": "patient/"+str(claim_data.mpi)
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
        response = send_claim_to_engine(fhir_msg)
        if response == "sucessfull":
            logger.info(f"Successfully submitted claim for MPI {claim_data.mpi} and VID {claim_data.vid}")
            bill.bill_status = "In Process"
            db.add(bill)
            db.commit()
            return {"detail": "Claim submitted successfully."}
        else:
            logger.error(f"Failed to submit claim for MPI {claim_data.mpi} and VID {claim_data.vid}: Engine responded with {response}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to submit claim to engine.")
    except Exception as e:
        logger.error(f"Error submitting claim: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while submitting the claim.")