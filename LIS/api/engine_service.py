from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import re


from fastapi import APIRouter, status, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from database import get_db
import model

router = APIRouter(tags=['Engine'])

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/engine_service.log", maxBytes=1000000, backupCount=1)
handler.setFormatter(formatter)
logger.addHandler(handler)

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

    Response payload shape:
    - `{ "message": str }`

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
        logger.info(f"Received new patient HL7 message:\n{data}")

        _, path = hl7_extract_paths(segment=data.splitlines()[1])
        values = get_hl7_value_by_path(data, path)
        
        dt = datetime.strptime(values['PID-7'], "%Y%m%d")
        date = dt.strftime("%Y-%m-%d")

        gender = "male" if values['PID-8'] == "M" else "female"

        patient = model.Patient(
            mpi = values['PID-3'],
            fname = values['PID-5.1'] if 'PID-5.1' in values else ' '.join(values.get('PID-5', '').split(' ')[:-1]), # here the last -1 is for last name.
            lname = values['PID-5.2'] if 'PID-5.2' in values else values.get('PID-5', '').split(' ')[-1],
            dob = date,
            gender = gender
        )

        db.add(patient)
        db.commit()
        db.refresh(patient)

        logger.info(f"Patient added successfully: {patient.fname + " " + patient.lname} (MPI: {patient.mpi})")
        return {"message": "Patient Added sucessfully"}

    except HTTPException as http_exp:
        logger.error(f"HTTP error processing new patient HL7 message: {str(http_exp.detail)}")
        raise
    except Exception as exp:
        logger.error(f"Error processing new patient HL7 message: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.post("/take_lab_order", status_code=status.HTTP_200_OK)
async def take_lab_order(req: Request, db: Session = Depends(get_db)):
    """
    Receive HL7 lab-order message and create LIS test requests.

    **Response (200 OK):**
    Returns JSON object with a message key. Possible values include:
    - `{ "message": "Lab order received successfully" }`
    - `{ "message": "No lab orders found in the message" }`
    - `{ "message": "MPI <id> not found in the database" }`

    **Error Responses:**
    - `400 Bad Request`: Malformed HL7 or processing error.
    """
    try:
        raw = await req.body()
        text_data = raw.decode("utf-8")
        logger.info(f"Received new lab order HL7 message:\n{text_data}")

        mpi = None
        lab_orders = []
        mpi_not_found = False
        for segment in text_data.splitlines()[1:]:
            _, paths = hl7_extract_paths(segment)
            path_to_values = get_hl7_value_by_path(segment, paths) # paths and values for 1 segment

            if "PID-1" in path_to_values.keys() and path_to_values["PID-1"] == "1":
                mpi = path_to_values.get("PID-3")
                continue
            if "OBR-1" not in path_to_values.keys() or not mpi:
                logger.warning(f"Skipping segment {segment} due to missing OBR-1 or MPI: {segment}")
                continue
            if "OBR-2" not in path_to_values.keys():
                logger.warning(f"Skipping segment {segment} due to missing OBR-2 (VID): {segment}")
                continue
            
            if db.get(model.Patient, mpi) is None: # if the mpi does not exists in the database.
                mpi_not_found = True
                break
            
            test_name = path_to_values.get("OBR-4.2", None)
            if not test_name:
                continue
            lab_orders.append(model.LabTestRequest(
                mpi = mpi,
                vid = path_to_values.get("OBR-2"),
                test_name= test_name # OBR-4.2 is the component of OBR-4 which contains the test name, if not found then set it as unknown test.
            ))
        
        if not mpi:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MPI not found in the message")
        
        if mpi_not_found:
            logger.critical(f"Lab order received for non-existent MPI: {mpi}. No orders were processed.")
            return {"message": f"MPI {mpi} not found in the database"}
        
        if not lab_orders:
            logger.warning(f"No lab orders found in the message for MPI: {mpi}")
            return {"message": "No lab orders found in the message"}

        db.add_all(lab_orders)
        db.commit()
        logger.info(f"Lab orders added successfully for MPI: {mpi}, Orders: {[order.test_name for order in lab_orders]}")

        return {"message": "Lab order received successfully"}

    except HTTPException as http_exp:
        logger.error(f"HTTP error processing new lab order HL7 message: {str(http_exp.detail)}")
        raise HTTPException(status_code=http_exp.status_code, detail=http_exp.detail)
    except Exception as exp:
        logger.error(f"Error processing new lab order HL7 message: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

# @router.put("/get-report-payment-status", tags=["Billing"])
# def update_payment(request: Request,  db: Session = Depends(get_db)):
#     """
#     Mark an existing bill as paid.

#     **Path Parameters:**
#     - `bill_id` (int, required): The unique identifier of the bill to mark as paid.

#     **Response (200 OK):**
#     Returns the updated billing record with:
#     - `payment_status`: Updated to "Paid"
#     - `updated_at`: Updated timestamp reflecting when the payment was recorded

#     **Note:**
#     - This endpoint does not require a request body. It simply flips `payment_status` to "Paid".
#     - No payment amount or method is validated; it is assumed payment is confirmed externally.

#     **Error Responses:**
#     - `404 Not Found`: No bill exists with the given `bill_id`
#     """
#     bill = db.get(model.LabTestBilling, bill_id)
#     if not bill:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found.")
        
#     bill.payment_status = "Paid"
#     bill.updated_at = datetime.now()
#     db.commit()
#     db.refresh(bill)
#     return bill

def hl7_extract_paths(segment) -> tuple[str, list[str]]:
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
    # segments = hl7_message.split('\n')[1:]
    segments = hl7_message.split('\n')
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