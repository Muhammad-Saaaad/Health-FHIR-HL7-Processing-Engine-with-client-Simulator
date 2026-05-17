from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import re


from fastapi import APIRouter, status, HTTPException, Request, Depends
import httpx
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

async def send_to_engine(data: str, url: str, system_id: str):
    """
    Send a FHIR data to the InterfaceEngine for routing to downstream services.

    Returns:
        str: The literal value `"sucessfull"` if the engine responds with HTTP 200.

    Raises:
        Exception: If the engine returns a non-200 status (e.g., 502 on partial downstream failure),
                   raises an exception with the engine's error detail so the caller can rollback.
    """
    try:
        logger.info(f"Sending data to engine: {data}")
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            headers = {"Content-Type": "text/plain", "System-Id": system_id}
            response = await client.post(url, content=data, headers=headers)
            if response.status_code == 200:
                logger.info(f"Successfully sent data to engine with url {url}")
                return "sucessfull"

            try:
                detail = response.json().get("detail", f"Engine returned {response.status_code}")
            except Exception:
                detail = response.text or f"Engine returned {response.status_code}"
            raise Exception(detail)

    except httpx.ReadTimeout:
        logger.error(f"Engine timed out for {url}")
        raise Exception(f"Engine did not respond in time for {url}")
    except Exception as exp:
        logger.error(f"Failed to send data to engine: {str(exp)}")
        raise


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
        - `PID-3`: NIC / CNIC (patient identifier)
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
    - `400 Bad Request`: Invalid or malformed HL7 message, missing `System-Id`, unknown lab ID, missing required PID fields, or DB error
    """
    try:
        # HL7 is sent as plain text — read raw bytes and decode
        lab_id = req.headers.get("System-Id", "Unknown")
        if lab_id == "Unknown":
            logger.warning("Received new patient HL7 message without System-Id header")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing System-Id header")
        
        if db.get(model.Lab, lab_id) is None:
            logger.warning(f"Received new patient HL7 message with unknown System-Id: {lab_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown System-Id: {lab_id}")
        
        raw = await req.body()
        data = raw.decode("utf-8")
        logger.info(f"Received new patient HL7 message:\n{data}")

        _, path = hl7_extract_paths(segment=data.splitlines()[1])
        values = get_hl7_value_by_path(data, path)

        if db.get(model.Patient, values['PID-3']) is not None:
            logger.info(f"Patient with NIC {values['PID-3']} already exists, skipping insert.")
            return {"message": f"Patient {values['PID-3']} already exists"}

        dt = datetime.strptime(values['PID-7'], "%Y%m%d")
        date = dt.strftime("%Y-%m-%d")

        gender = "male" if values['PID-8'] == "M" else "female"

        patient = model.Patient(
            lab_id = lab_id,
            nic = values['PID-3'],
            fname = values['PID-5.1'] if 'PID-5.1' in values else ' '.join(values.get('PID-5', '').split(' ')[:-1]), # here the last -1 is for last name.
            lname = values['PID-5.2'] if 'PID-5.2' in values else values.get('PID-5', '').split(' ')[-1],
            dob = date,
            gender = gender
        )

        db.add(patient)
        db.commit()
        db.refresh(patient)

        logger.info(f"Patient added successfully: {patient.fname + " " + patient.lname} (NIC: {patient.nic}, Lab ID: {patient.lab_id})")
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

    The `System-Id` request header must contain a valid LIS `lab_id`.
    The patient identifier is read from `PID-3` and stored as `nic`.

    **Response (200 OK):**
    Returns JSON object with a message key. Possible values include:
    - `{ "message": "Lab order received successfully" }`
    - `{ "message": "No lab orders found in the message" }`
    - `{ "message": "NIC <id> not found in the database" }`

    **Error Responses:**
    - `400 Bad Request`: Malformed HL7, missing `System-Id`, unknown lab ID, missing NIC, or processing error.
    """
    try:
        raw = await req.body()
        text_data = raw.decode("utf-8")
        logger.info(f"Received new lab order HL7 message:\n{text_data}")

        lab_id = req.headers.get("System-Id", "Unknown")
        if lab_id == "Unknown":
            logger.warning("Received lab order HL7 message without System-Id header")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing System-Id header")
        
        if db.get(model.Lab, lab_id) is None:
            logger.warning(f"Received lab order HL7 message with unknown System-Id: {lab_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown System-Id: {lab_id}")

        nic = None
        lab_orders = []
        nic_not_found = False
        for segment in text_data.splitlines()[1:]:
            _, paths = hl7_extract_paths(segment)
            path_to_values = get_hl7_value_by_path(segment, paths) # paths and values for 1 segment

            if "PID-1" in path_to_values.keys() and path_to_values["PID-1"] == "1":
                nic = path_to_values.get("PID-3")
                continue
            if "OBR-1" not in path_to_values.keys() or not nic:
                logger.warning(f"Skipping segment {segment} due to missing OBR-1 or NIC: {segment}")
                continue
            if "OBR-2" not in path_to_values.keys():
                logger.warning(f"Skipping segment {segment} due to missing OBR-2 (VID): {segment}")
                continue
            
            patient = db.get(model.Patient, nic)
            if patient is None or patient.lab_id != lab_id:
                nic_not_found = True
                break
            
            test_code = path_to_values.get("OBR-4.1", None)
            test_name = path_to_values.get("OBR-4.2", None)
            if not test_name:
                continue
            if db.query(model.LabTest).filter(model.LabTest.test_code == test_code).first() is None:
                logger.warning(f"Unknown test code {test_code} in segment: {segment}")
                continue
            lab_orders.append(model.LabTestRequest(
                nic=nic,
                lab_id=lab_id,
                vid = path_to_values.get("OBR-2"), # add test code here.
                test_name= test_name, # OBR-4.2 is the component of OBR-4 which contains the test name, if not found then set it as unknown test.
            ))
        
        if not nic:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NIC not found in the message")
        
        if nic_not_found:
            logger.critical(f"Lab order received for non-existent NIC: {nic}. No orders were processed.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": f"NIC {nic} not found in the database"})
        
        if not lab_orders:
            logger.warning(f"No lab orders found in the message for NIC: {nic}")
            # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "No lab orders found in the message"})
            return {"message": "No lab orders found in the message"}

        db.add_all(lab_orders)
        db.commit()
        logger.info(f"Lab orders added successfully for NIC: {nic}, Orders: {[order.test_name for order in lab_orders]}")

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
