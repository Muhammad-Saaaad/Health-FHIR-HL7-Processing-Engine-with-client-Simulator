from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy.orm import Session

from database import get_db
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
# PID|1||23||saad^Muhammad||20041006|M|||||
# IN1|||||||||||||||Silver|||||||||||||||||||||9||||||||||||||||

@router.post("/get/registed_patient")
async def get_registed_patient(req: Request, db: Session = Depends(get_db)):
    """
    Internal engine endpoint to receive a patient from an HL7 v2.x message (plain text).

    This endpoint is called by the InterfaceEngine when it delivers an HL7 ADT message
    to the Payer system. It parses PID (patient demographics) and IN1 (insurance) segments
    to match an existing pre-registered patient and update their MPI from the EHR.

    **Request Body:** Raw HL7 v2.x message as plain text (Content-Type: text/plain)

    **PID fields extracted:**
    - `PID-3`: MPI (used to update the patient)
    - `PID-5` / `PID-5.1` / `PID-5.2`: Name (used for logging/context)
    - `PID-7`: Date of birth (YYYYMMDD) — used to match existing patient
    - `PID-8`: Gender — used to match existing patient

    **IN1 fields used:**
    - `IN1-36` (or `IN1-2` as fallback): Policy number — used to match the existing InsurancePolicy record
    - `IN1-15` (or `IN1-3` as fallback): Plan type — used to match the existing InsurancePolicy record

    **Upsert Logic:**
    - Looks up an existing Patient by gender + date_of_birth + policy_id match.
    - If found: updates their MPI and returns 200.
    - If not found: returns 404 (patient must be pre-registered via the Payer `/reg_patient` endpoint first).

    **Response (200 OK):**
    - `{"message": "Patient MPI updated successfully"}` if the patient was located and MPI updated

    **Error Responses:**
    - `400 Bad Request`: Malformed HL7, missing required PID/IN1 fields, or DB error
    - `404 Not Found`: No matching pre-registered patient found for the incoming HL7 data
    """
    try:
        # HL7 is sent as plain text — read raw bytes and decode
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
    mpi = int(all_values['PID-3'].strip())

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
        # Patient already registered in Payer — just update the MPI
        logger.info(f"Found existing patient for HL7 data. Updating MPI to {mpi} for patient ID {existing_patient.id}")
        existing_patient.mpi = mpi
        db.commit()
        db.refresh(existing_patient)
        # return {"message": "Patient MPI updated successfully"}
        return JSONResponse(content={"message": "Patient MPI updated successfully"}, status_code=status.HTTP_200_OK)
    else:
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        logger.info(f"Patient not found for HL7 data. Attempting to register new patient.")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8003/reg_patient",
                json={
                    "mpi": mpi,
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

        mpi = all_values.get('PID-3')
        vid = all_values.get('PV1-19') or all_values.get('PV1-20')
        if not mpi or not vid:
            logger.error(f"Missing required MPI or VID in claim submission from engine: {data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required MPI or VID in claim submission")
        
        is_patient = db.query(models.Patient).filter(models.Patient.mpi == int(mpi.strip())).first()

        if not is_patient:
            logger.error(f"No patient found with MPI {mpi.strip()} for claim submission from engine: {data}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No patient found with MPI {mpi.strip()} for claim submission")

        policy = db.query(models.InsurancePolicy).filter(models.InsurancePolicy.pid == is_patient.pid).first()
        if not policy:
            logger.error(f"No insurance policy found for patient with MPI {mpi.strip()} for claim submission from engine: {data}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No insurance policy found for patient with MPI {mpi.strip()} for claim submission")

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
        logger.info(f"Successfully added claim to db for patient with MPI {mpi.strip()} from claim submission from engine: {data}")
        return JSONResponse(content={"message": "Claim received successfully"}, status_code=status.HTTP_200_OK)
    except Exception as exp:
        logger.error(f"Error processing claim submission from engine: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

def hl7_extract_paths(segment):
    """
    Parse a single HL7 segment string and return all field/component/subcomponent paths.

    Generates dot-notation paths such as:
    - `PID-3` (simple field)
    - `PID-5.1` (component within a field, split by `^`)
    - `PID-5.1.2` (subcomponent within a component, split by `&`)

    Args:
        segment (str): A single HL7 segment string (e.g., "PID|1||12345^^^MR||Smith^John").

    Returns:
        tuple: (segment_type: str, paths: list[str])
            - `segment_type`: The segment identifier (e.g., "PID", "IN1").
            - `paths`: List of all non-empty field paths found in the segment.
    """
    paths = []
    fields = segment.split('|')
    segment_type = fields[0]  # PID, IN1, etc.
    for i, field in enumerate(fields[1:], start=1):
        if field == '':
            continue
        if '^' in field:
            components = field.split('^')
            for j, component in enumerate(components, start=1):
                if '&' in component:
                    subcomponents = component.split('&')
                    for k, subcomponent in enumerate(subcomponents, start=1):
                        paths.append(f"{segment_type}-{i}.{j}.{k}")
                else:
                    paths.append(f"{segment_type}-{i}.{j}")
        else:
            paths.append(f"{segment_type}-{i}")
    return (segment_type, paths)


def get_hl7_value_by_path(hl7_message, paths):
    """
    Extract field values from a full HL7 message for a given list of dot-notation paths.

    Iterates over all segments in the message and resolves each path, handling field-level,
    component-level (`^`), and subcomponent-level (`&`) access with bounds checking.

    Args:
        hl7_message (str): Full HL7 v2.x message string with segments separated by newlines.
        paths (list[str]): List of paths to extract (e.g., ["PID-3", "PID-5.1", "IN1-3"]).

    Returns:
        dict: A mapping of path -> extracted value (e.g., {"PID-3": "12345", "PID-5.1": "Smith"}).
              Paths with no data at their location return an empty string.
    """
    segments = hl7_message.split('\n')[1:]
    value = {}
    for segment in segments:
        for path in paths:
            sp_path = re.split(r"-|\.", path)  # [PID, 5, 2, 1]
            fields = segment.split("|")

            if fields[0] == sp_path[0]:
                field_val = fields[int(sp_path[1])] if int(sp_path[1]) < len(fields) else ''

                if "^" in field_val and len(sp_path) > 2:
                    components = field_val.split("^")
                    comp = components[int(sp_path[2]) - 1] if int(sp_path[2]) - 1 < len(components) else ''
                    if "&" in comp and len(sp_path) > 3:
                        sub_components = comp.split("&")
                        value[path] = sub_components[int(sp_path[3]) - 1] if int(sp_path[3]) - 1 < len(sub_components) else ''
                    else:
                        value[path] = comp
                else:
                    value[path] = field_val
    return value