from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy.orm import Session

from database import get_db
from hl7_validation import get_hl7_value_by_path, hl7_extract_paths
import models

router = APIRouter(tags=["Engine"])

logger = logging.getLogger("engine_service")
logger.setLevel(logging.INFO)
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")
handler = RotatingFileHandler(
    r"logs\engine_service.log",
    maxBytes=20000, # 20KB
    backupCount=1
)
handler.setFormatter(formater)
logger.addHandler(handler)

# MSH|^~\\&|EHR||payer||20260203120000||ADT^A01|MSG00001|P|2.5
# PID|1||37201-7687308-3||saad^Muhammad||20041006|M|||||
# IN1|||||||||||||||Silver|||||||||||||||||||||9||||||||||||||||

@router.post("/get/registed_patient")
async def get_registed_patient(req: Request, db: Session = Depends(get_db)):
    """
    Internal engine endpoint to receive a patient from an HL7 v2.x message (plain text).

    This endpoint is called by the InterfaceEngine when it delivers an HL7 ADT message
    to the Payer system. It parses PID (patient demographics) and IN1 (insurance) segments
    to match an existing pre-registered patient and update their NIC from the EHR.

    **Request Body:** Raw HL7 v2.x message as plain text (Content-Type: text/plain)

    **PID fields extracted:**
    - `PID-3`: NIC (used to update the patient)
    - `PID-5` / `PID-5.1` / `PID-5.2`: Name (used for logging/context)
    - `PID-7`: Date of birth (YYYYMMDD) — used to match existing patient
    - `PID-8`: Gender — used to match existing patient

    **IN1 fields used:**
    - `IN1-36` (or `IN1-2` as fallback): Policy number — used to match the existing InsurancePolicy record
    - `IN1-15` (or `IN1-3` as fallback): Plan type — used to match the existing InsurancePolicy record

    **Upsert Logic:**
    - Looks up an existing Patient by gender + date_of_birth + policy_id match.
    - If found: updates their NIC and returns 200.
    - If not found: returns 404 (patient must be pre-registered via the Payer `/reg_patient` endpoint first).

    **Response (200 OK):**
    - `{"message": "Patient NIC updated successfully"}` if the patient was located and NIC updated

    **Error Responses:**
    - `400 Bad Request`: Malformed HL7, missing required PID/IN1 fields, or DB error
    - `404 Not Found`: No matching pre-registered patient found for the incoming HL7 data
    """
    try:
        # HL7 is sent as plain text — read raw bytes and decode
        insurance_id = req.headers.get("System-Id", "Unknown")
        if insurance_id == "Unknown":
            logger.warning("Received new patient HL7 message without System-Id header")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing System-Id header")
        
        if db.get(models.Insurance, insurance_id) is None:
            logger.warning(f"Received new patient HL7 message with unknown System-Id: {insurance_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown System-Id: {insurance_id}")
        
        raw = await req.body()
        data = raw.decode("utf-8", errors="replace")
        logger.info(f"Received HL7 message for patient registration: {data}")

        # Parse all segments
        all_values = {}
        for segment in data.splitlines()[1:]:
            if not segment.strip():
                logger.warning(f"Skipping empty HL7 segment in message: {data}")
                continue
            _, paths = hl7_extract_paths(segment=segment)
            segment_values = get_hl7_value_by_path(data, paths)
            all_values.update(segment_values)

        logger.info(f"Extracted values from HL7 message: {all_values}")
        # --- Extract from PID ---
        dt = datetime.strptime(all_values['PID-7'], "%Y%m%d")
        date_of_birth = dt.strftime("%Y-%m-%d")
        gender = "Male" if str(all_values.get('PID-8')).strip() == "M" else "Female"

        if 'PID-5.1' in all_values or 'PID-5.2' in all_values: # hl7 cannot have a full name you should always break it down.
            fname = all_values.get('PID-5.1', '')
            lname = all_values.get('PID-5.2', '')
            name = f"{fname} {lname}".strip()
        else:
            name = all_values.get('PID-5', '')
        
        phone_no = all_values.get('PID-13') or all_values.get('PID-14') or None

    except HTTPException as http_exp:
        logger.error(f"HTTPException: {http_exp.detail} while processing HL7 message: {data}")
        raise
    except Exception as exp:
        logger.error(f"Unexpected error while processing HL7 message: {data}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

    # --- Upsert logic ---
    # Match on gender + date_of_birth (from PID) + policy_id (from IN1)
    # policy_id from IN1 maps to InsurancePolicy.policy_id
    policy_id = all_values.get('IN1-36') or all_values.get('IN1-2')
    plan_type = all_values.get('IN1-15') or all_values.get('IN1-3')
    if not all_values.get("PID-3"):
        logger.error(f"Missing required PID-3 field in HL7 message: {data}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required PID-3 field")
    nic = all_values['PID-3'].strip()

    if not policy_id:
        logger.warning(f"Missing policy ID in IN1 segment of HL7 message: {data}. Cannot match patient without policy ID.")
        policy_id= "0"
    if not plan_type:
        logger.warning(f"Missing plan type in IN1 segment of HL7 message: {data}. Cannot match patient without plan type.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required IN1-15 or IN1-3 field for plan type")
        
    existing_patient = (
        db.query(models.Patient)
        .join(models.InsurancePolicy, models.InsurancePolicy.policy_id == int(str(policy_id).strip()))
        .filter(
            models.Patient.gender == gender,
            models.Patient.date_of_birth == date_of_birth,
            models.InsurancePolicy.policy_id == int(str(policy_id).strip()),
            models.InsurancePolicy.category_name == str(plan_type).strip()
        )
        .first()
    )

    if existing_patient:
        # Patient already registered in Payer — just update the NIC
        logger.info(f"Found existing patient for HL7 data. Updating NIC to {nic} for patient ID {existing_patient.pid}")
        existing_patient.nic = nic
        db.commit()
        db.refresh(existing_patient)
        return JSONResponse(content={"message": "Patient NIC updated successfully"}, status_code=status.HTTP_200_OK)
    else:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        logger.info(f"Patient not found for HL7 data. Attempting to register new patient.")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8003/reg_patient/"+str(insurance_id).strip(),
                json={
                    "nic": nic,
                    "name": name,
                    "phone_no": phone_no,
                    "gender": gender,
                    "date_of_birth": date_of_birth,
                    "user_id": 0, # since we don't have a user_id here, we can set it to 0 or any default value. The reg_patient endpoint should handle this accordingly.
                    "insurance_type": plan_type
                }
            )
            if response.status_code == 201:
                logger.info(f"Successfully registered new patient via /reg_patient endpoint for HL7.")
                return JSONResponse(
                    content={"message": "Patient not found, but registration endpoint was called to create a new patient."},
                    status_code=status.HTTP_200_OK
                )
            else:
                logger.error(f"Failed to register new patient via /reg_patient endpoint for HL7 data: {data}")
                return JSONResponse(
                    content={"message": "Patient not found, and registration endpoint failed to create a new patient. error: " + response.text},
                    status_code=status.HTTP_404_NOT_FOUND
                )

@router.post("/submit-claim")
async def submit_claim_from_engine(req: Request, db: Session = Depends(get_db)):
    """
    Internal engine endpoint to receive a claim submission from the InterfaceEngine.

    This is called by the InterfaceEngine when it delivers a claim submission (FHIR Claim resource)
    to the Payer system. The endpoint should process the claim and return a 200 OK if successful.
    """
    try:
        insurance_id = req.headers.get("System-Id", "Unknown")
        if insurance_id == "Unknown":
            logger.warning("Received new patient HL7 message without System-Id header")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing System-Id header")
        
        if db.get(models.Insurance, insurance_id) is None:
            logger.warning(f"Received new patient HL7 message with unknown System-Id: {insurance_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown System-Id: {insurance_id}")
        
        raw = await req.body()
        data = raw.decode("utf-8", errors="replace")
        logger.info(f"Received HL7 claim submission: {data}")

        # Parse all segments
        all_values = {}
        for segment in data.splitlines()[1:]:
            if not segment.strip():
                logger.warning(f"Skipping empty HL7 segment in message: {data}")
                continue
            _, paths = hl7_extract_paths(segment=segment)
            segment_values = get_hl7_value_by_path(data, paths)
            all_values.update(segment_values)

        logger.info(f"Extracted values from claim HL7 message: {all_values}")

        nic = all_values.get('PID-3')
        vid = all_values.get('PV1-19') or all_values.get('PV1-20')
        if not nic or not vid:
            logger.error(f"Missing required NIC or VID in claim submission from engine: {data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required nic or VID in claim submission")
        
        is_patient = db.query(models.Patient).filter(models.Patient.nic == nic.strip(), models.Patient.insurance_id == insurance_id).first()

        if not is_patient:
            logger.error(f"No patient found with NIC {nic.strip()} in insurance {insurance_id} for claim submission from engine: {data}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No patient found with NIC {nic.strip()} in insurance {insurance_id} for claim submission")

        policy = db.query(models.InsurancePolicy).filter(models.InsurancePolicy.pid == is_patient.pid).first()
        if not policy:
            logger.error(f"No insurance policy found for patient with NIC {nic.strip()} in insurance {insurance_id} for claim submission from engine: {data}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No insurance policy found for patient with NIC {nic.strip()} in insurance {insurance_id} for claim submission")

        dt = datetime.strptime(all_values.get('FT1-4'), "%Y%m%d%H%M%S")
        date_time = dt.strftime("%Y-%m-%d %H:%M:%S")

        service_included = True
        tests_included = False
        if all_values.get('FT1-7', "") == "Service_LabTest":
            tests_included = True
        total_fee = float(all_values.get('FT1-8', 0))

        new_claim = models.PatientClaim(
            policy_id = policy.policy_id,
            pid = is_patient.pid,
            vid = int(vid.strip()),
            service_included = service_included,
            tests_included = tests_included,
            bill_amount = total_fee,
            created_at = date_time
        )
        db.add(new_claim)
        db.commit()
        logger.info(f"Successfully added claim to db for patient with NIC {nic.strip()} from claim submission from engine: {data}")
        return JSONResponse(content={"message": "Claim received successfully"}, status_code=status.HTTP_200_OK)
    except Exception as exp:
        logger.error(f"Error processing claim submission from engine: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

async def claim_response_to_engine(url: str, data: str, system_id: str):
    response = None
    try:
        logger.info(f"Sending claim response to engine: {data}")

        headers = {"Content-Type": "text/plain", "System-Id": system_id}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            response = await client.post(url, content=data, headers=headers)

        if response.status_code in (200, 201):
            logger.info(f"Successfully sent claim response to engine")
            return "successfull"

        try:
            detail = response.json().get("detail", f"Engine returned {response.status_code}")
        except Exception:
            detail = response.text or f"Engine returned {response.status_code}"
        raise Exception(detail)

    except httpx.RequestError as req_err:
        logger.exception(f"HTTP request error while sending claim to engine: {str(req_err)}")
        raise Exception(f"HTTP request error: {str(req_err)}") from req_err
    except Exception as exp:
        # Re-raise so the calling endpoint knows delivery failed
        response_repr = f"status={response.status_code}" if response is not None else "no response (request never completed)"
        logger.exception(f"Failed to send claim to engine: {str(exp)} ({response_repr})")
        raise
