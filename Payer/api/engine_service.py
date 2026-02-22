from datetime import datetime
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter(tags=["Engine"])

@router.post("/get/registed_patient", status_code=status.HTTP_200_OK)
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
    - `IN1-3` (or `IN1-2` as fallback): Policy number — used to match the existing InsurancePolicy record

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
        data = raw.decode("utf-8")

        # Parse all segments
        all_values = {}
        for segment in data.split('\n')[1:]:
            if not segment.strip():
                continue
            _, paths = hl7_extract_paths(segment=segment)
            segment_values = get_hl7_value_by_path(data, paths)
            all_values.update(segment_values)

        # --- Extract from PID ---
        dt = datetime.strptime(all_values['PID-7'], "%Y%m%d")
        date = dt.strftime("%Y-%m-%d")
        gender = "Male" if all_values.get('PID-8') == "M" else "Female"

        if 'PID-5.1' in all_values or 'PID-5.2' in all_values: # hl7 cannot have a full name you should always break it down.
            fname = all_values.get('PID-5.1', '')
            lname = all_values.get('PID-5.2', '')
            name = f"{fname} {lname}".strip()
        else:
            name = all_values.get('PID-5', '')

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

    # --- Upsert logic ---
    # Match on gender + date_of_birth (from PID) + policy_id (from IN1)
    # policy_number from IN1 maps to InsurancePolicy.policy_id
    policy_number = all_values.get('IN1-3') or all_values.get('IN1-2')

    existing_patient = (
        db.query(models.Patient)
        .join(models.InsurancePolicy, models.InsurancePolicy.pid == models.Patient.pid)
        .filter(
            models.Patient.gender == gender,
            models.Patient.date_of_birth == date,
            models.InsurancePolicy.policy_id == int(policy_number)
        )
        .first()
    )

    if existing_patient:
        # Patient already registered in Payer — just update the MPI
        existing_patient.mpi = all_values['PID-3']
        db.commit()
        db.refresh(existing_patient)
        return {"message": "Patient MPI updated successfully"}
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")


def hl7_extract_paths(segment) -> (str, list[str]):
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