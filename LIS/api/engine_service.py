from datetime import datetime
import re


from fastapi import APIRouter, status, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from database import get_db
import model

router = APIRouter(tags=['Engine'])


@router.post("/get/new-patient", status_code=status.HTTP_200_OK)
async def add_patient(req: Request, db: Session = Depends(get_db)):
    """
    Internal engine endpoint to receive and process a new patient from an HL7 v2.x message.

    This endpoint is called exclusively by the InterfaceEngine when it receives a new HL7 ADT
    (Admit, Discharge, Transfer) message. It parses the raw HL7 message body to extract patient
    demographic data from the PID segment and stores it in the LIS database.

    **Request Body (raw HL7 v2.x message as plain text):**
    - A multi-line HL7 message string. The PID segment is expected on line 2 (index 1).
    - Key PID fields extracted:
        - `PID-3`: MPI (Master Patient Index / Patient ID)
        - `PID-5` or `PID-5.1` / `PID-5.2`: Patient first and last name
        - `PID-7`: Date of birth in `YYYYMMDD` format (converted to `YYYY-MM-DD`)
        - `PID-8`: Gender code (`M` → "male", anything else → "female")

    **Response (200 OK):**
    Returns a confirmation message:
    - `message`: "Patient Added sucessfully"

    **Note:**
    - This is an internal service-to-service endpoint. Do not call this directly from the front-end.
    - HL7 component separators (`^`) and sub-component separators (`&`) are both handled.

    **Error Responses:**
    - `400 Bad Request`: Invalid or malformed HL7 message, missing required PID fields, or DB error
    """
    try:
        # HL7 is sent as plain text — read raw bytes and decode
        raw = await req.body()
        data = raw.decode("utf-8")

        _, path = hl7_extract_paths(segment=data.split('\n')[1])
        values = get_hl7_value_by_path(data, path)
        
        dt = datetime.strptime(values['PID-7'], "%Y%m%d")
        date = dt.strftime("%Y-%m-%d")

        gender = "male" if values['PID-8'] == "M" else "female"

        patient = model.Patient(
            mpi = values['PID-3'],
            fname = values['PID-5.1'] if 'PID-5.1' in values else values.get('PID-5', '').split(' ')[0],
            lname = values['PID-5.2'] if 'PID-5.2' in values else ' '.join(values.get('PID-5', '').split(' ')[1:]),
            dob = date,
            gender = gender
        )

        db.add(patient)
        db.commit()
        db.refresh(patient)

        return {"message": "Patient Added sucessfully"}

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

def hl7_extract_paths(segment):
    """
    Parse a single HL7 segment string and return all field/component/subcomponent paths.

    Generates dot-notation path strings such as:
    - `PID-3` for a simple field
    - `PID-5.1` for the first component within a field (split by `^`)
    - `PID-5.1.2` for a subcomponent (split by `&`)

    Args:
        segment (str): A single HL7 v2.x segment string (e.g., "PID|1||12345^^^MR||Smith^John").

    Returns:
        tuple: (segment_type: str, paths: list[str])
            - `segment_type`: The segment identifier (e.g., "PID").
            - `paths`: List of all non-empty path strings found in the segment.
    """
    paths = []

    # for segment in segments[1:]:
    fields = segment.split('|')
    segment_type = fields[0] # PID etc.
    for i , field in enumerate(fields[1:], start=1):
        if field == '':
            continue
        if '^' in field:
            components = field.split('^')
            for j, component in enumerate(components, start=1):
                if '&' in component:
                    subcomponents = component.split('&')
                    for k, subcomponent in enumerate(subcomponents, start=1):
                        path = f"{segment_type}-{i}.{j}.{k}"
                        paths.append(path)
                else:
                    path = f"{segment_type}-{i}.{j}"
                    paths.append(path)
        else:
            path = f"{segment_type}-{i}"
            paths.append(path)
    return (segment_type, paths)

def get_hl7_value_by_path(hl7_message, paths): 
    """
    Extract values from a full HL7 message for a given list of dot-notation paths.

    Iterates over all segments in the message and resolves each path, handling field,
    component (`^`), and subcomponent (`&`) levels.

    Args:
        hl7_message (str): Full HL7 v2.x message string with segments separated by newlines.
        paths (list[str]): List of paths to extract (e.g., ["PID-3", "PID-5.1"]).

    Returns:
        dict: A mapping of path -> extracted string value.
              Returns empty string for paths not found or out of bounds.
    """
    segments = hl7_message.split('\n')[1:]
    value = {}
    for segment in segments:
        for path in paths:
            sp_path = re.split(r"-|\.", path) # [PID, 5, 2, 1]
           
            fields = segment.split("|")

            if fields[0] == sp_path[0]:

                if "^" in fields[int(sp_path[1])]:
                    components = fields[int(sp_path[1])].split("^")
                    
                    if "&" in components[int(sp_path[2])-1]:
                        sub_components = components[int(sp_path[2])-1].split("&")
                        value[path] = sub_components[int(sp_path[3])-1]
                    else:
                        value[path] = components[int(sp_path[2])-1] 
                else:
                    value[path] = fields[int(sp_path[1])]
        
    return value