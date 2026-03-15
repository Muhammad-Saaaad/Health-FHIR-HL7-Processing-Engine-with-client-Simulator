import os
import re
import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from schemas.endpoint import AddEndpoint
import models
from database import get_db
from validation.fhir_validation import validate_unknown_fhir_resource, fhir_extract_paths
from validation.hl7_validation import hl7_extract_paths

router = APIRouter(tags=["Endpoint"])

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("mapping_logger")
logger.setLevel(logging.INFO)

formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

if not logger.handlers:
    rotating_file_handler = RotatingFileHandler(
        r"./logs/mapping.log",
        maxBytes=20000, # 20KB
        backupCount=1
    )
    rotating_file_handler.setFormatter(formater)
    logger.addHandler(rotating_file_handler)

canonical_paths = {
    # FHIR — Patient resource  (prefix = "Patient-")
    "Patient-identifier[0].value": "mpi",
    "Patient-name[0].text": "fullname",
    "Patient-name[0].given": "given name",
    "Patient-name[0].family[0]": "family name",
    "Patient-gender": "gender",
    "Patient-birthDate": "birth date",
    "Patient-telecom[0].value": "phone number",
    "Patient-address[0].text": "address",

    # FHIR — Coverage resource  (prefix = "Coverage-")
    "Coverage-identifier[0].value": "policy number",
    "Coverage-type.coding[0].code": "plan type",

    # HL7 — PID segment
    "PID-3": "mpi",
    "PID-5": "fullname",
    "PID-5.1": "family name",
    "PID-5.2": "given name",
    "PID-7": "birth date",
    "PID-8": "gender",
    "PID-11": "address",
    "PID-13": "phone number",

    # HL7 — IN1 segment
    "IN1-2": "policy number",
    "IN1-15": "plan type"
}

@router.get("/server-endpoint/{server_id}", status_code=status.HTTP_200_OK)
def server_endpoint(server_id: int, db:Session = Depends(get_db)):
    """
    Retrieve all registered endpoints belonging to a specific server.

    **Path Parameters:**
    - `server_id` (int, required): The unique ID of the server whose endpoints to retrieve.

    **Response (200 OK):**
    Returns a list of endpoint objects registered under the given server. Each object includes:
    - `endpoint_id`: Unique endpoint identifier
    - `server_id`: The parent server's ID
    - `url`: The endpoint URL

    **Note:**
    - Returns an empty list if the server has no registered endpoints.

    **Error Responses:**
    - `404 Not Found`: No server exists with the given `server_id`
    - `400 Bad Request`: Unexpected database error
    """
    if not db.get(models.Server, server_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"server id {server_id} does not exists")
    try:
        data = db.query(models.Endpoints).filter(models.Endpoints.server_id == server_id).all()
        return data

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.post("/add-endpoint", status_code=status.HTTP_201_CREATED)
def add_endpoint(endpoint: AddEndpoint, db: Session = Depends(get_db)):
    """
    Register a new endpoint for a server and auto-extract its field mappings from a sample message.

    This is a key configuration step in the Interface Engine. After registering an endpoint,
    the engine parses the provided sample message (FHIR or HL7) to automatically discover
    available fields and stores them as `EndpointFields` — which are then used when building routes.

    **Request Body:**
    - `server_id` (int, required): ID of the server this endpoint belongs to. Must exist.
    - `url` (str, required): The endpoint URL. Must be unique per server.
    - `server_protocol` (str, required): Protocol of the message format — `"FHIR"` or `"HL7"`.
    - `sample_msg` (dict | str, required): A sample message in the specified protocol format.
        - For `"FHIR"`: Provide a JSON object — either a single FHIR resource or a FHIR Bundle.
        - For `"HL7"`: Provide a raw HL7 v2.x string with segments separated by newlines (`\\n`).

    **Response (201 Created):**
    Returns a confirmation message:
    - `message`: "Endpoint added successfully"

    **Side Effects:**
    - Parses the `sample_msg` to extract field paths.
    - Matches extracted paths against the canonical mapping table to assign human-readable names.
    - Stores the discovered fields as `EndpointField` records in the database, linked to this endpoint.
    - Unrecognized paths are logged as warnings and skipped.

    **Supported Canonical Field Names:**
    `mpi`, `fullname`, `given name`, `family name`, `gender`, `birth date`, `phone number`, `address`

    **Constraints:**
    - `server_id` must refer to an existing server.
    - The URL must be unique within the same server.
    - `server_protocol` must be either `"FHIR"` or `"HL7"` (case-sensitive).

    **Error Responses:**
    - `400 Bad Request`: Server does not exist
    - `400 Bad Request`: URL already exists for this server
    - `400 Bad Request`: Failed to extract fields from the provided sample message
    """
    if not db.get(models.Server, endpoint.server_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server does not exist")

    if db.query(models.Endpoints).filter(models.Endpoints.server_id == endpoint.server_id, 
                                            models.Endpoints.url == endpoint.url).first():
        
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="URL already exists")
    
    if endpoint.sample_msg in [None, "", {}]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Sample message is required to extract endpoint fields")

    if endpoint.server_protocol not in ["FHIR", "HL7"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Server Protocol is not FHIR or HL7")

    try:
        new_endpoint = models.Endpoints(
            server_id=endpoint.server_id,
            url=endpoint.url,
        )
        db.add(new_endpoint)
        db.flush()

        if endpoint.server_protocol == "FHIR":
            is_valid, message = validate_unknown_fhir_resource(endpoint.sample_msg)
            if not is_valid:
                logger.error("Invalid FHIR sample message: ",message)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
            
            add_fhir_endpoint_fields(
                endpoint_id=new_endpoint.endpoint_id,
                sample_msg=endpoint.sample_msg, db=db
            )
            logger.info("FHIR endpoint fields added sucessfully")
        else: # if not FHIR then it should be HL7
            add_hl7_endpoint_fields(
                endpoint_id=new_endpoint.endpoint_id,
                sample_msg=endpoint.sample_msg.strip(), db=db
            )
            logger.info("Hl7 endpoint fields added sucessfully")
        db.commit()
        return {"message": "Endpoint added successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")


@router.get("/endpoint_field_path/{endpoint_id}", status_code=status.HTTP_200_OK)
def endpoint_field_paths(endpoint_id: int, db:Session = Depends(get_db)):
    """
    Retrieve all discovered fields for a specific endpoint.

    This is used when configuring a new route — you call this endpoint for both the source
    and destination endpoint to get the list of available fields, then use those field IDs
    in the route's mapping rules.

    **Path Parameters:**
    - `endpoint_id` (int, required): The unique ID of the endpoint whose fields to retrieve.

    **Response (200 OK):**
    Returns a list of endpoint field objects. Each item includes:
    - `endpoint_filed_id`: Unique field identifier (used as `src_paths` / `dest_paths` in route rules)
    - `endpoint_id`: The parent endpoint's ID
    - `resource`: The FHIR resource type or HL7 segment (e.g., "Patient", "PID")
    - `path`: The field path in dot/bracket notation (e.g., "name[0].text", "PID-5.1")
    - `name`: The canonical human-readable field name (e.g., "fullname", "mpi")

    **Error Responses:**
    - `404 Not Found`: No endpoint exists with the given `endpoint_id`
    - `400 Bad Request`: Unexpected database error
    """
    if not db.get(models.Endpoints, endpoint_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"endpoint id {endpoint_id} does not exists")

    try:    
        data = db.query(models.EndpointFileds).filter(models.EndpointFileds.endpoint_id == endpoint_id).all()
        return data

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


def add_fhir_endpoint_fields(endpoint_id: int, sample_msg: str,  db: Session) -> bool: # uses the old session
    """
    Internal helper: parse a FHIR sample message, extract field paths, map them to canonical
    names, and persist them as EndpointField records for the given endpoint.

    Supports both single FHIR resources and FHIR Bundle messages.
    Fields not found in the canonical_paths table are skipped and logged as warnings.

    Args:
        endpoint_id (int): The ID of the endpoint to attach discovered fields to.
        sample_msg (dict): A parsed FHIR JSON message — either a resource or a Bundle.
        db (Session): Active SQLAlchemy database session.

    Returns:
        True on success.

    Raises:
        HTTPException (400): If any error occurs during path extraction or DB operations.
    """
    try:
        print(sample_msg)
        paths = []
        if sample_msg['resourceType'] != 'Bundle': 
            resource_type = sample_msg['resourceType']
            raw_paths = fhir_extract_paths(sample_msg)
            # Prefix each path with the resource type so identical paths in
            # different resources resolve to different canonical names.
            # e.g. "identifier[0].value" → "Patient-identifier[0].value"
            paths = [f"{resource_type}-{p}" for p in raw_paths]

        else:
            for entry in sample_msg['entry']:
                resource_type = entry['resource']['resourceType']
                raw_paths = fhir_extract_paths(entry['resource'])
                # Prefix with resource type for the same reason as above.
                paths = [f"{resource_type}-{p}" for p in raw_paths]
        
        if len(paths) > 0:
            endpoint_fields = {}
            for path in paths:

                if path in canonical_paths: # if multiple fields map to same name the previous ones are overwritten
                    name = canonical_paths[path]
                    endpoint_fields[name] = path
                    logger.info(f"Mapped field {name} to path {path}")
                else:
                    logger.warning(f"No canonical mapping found for path {path}, skipping.")
            
            new_fields = []
            for name, path in endpoint_fields.items():
                field = models.EndpointFileds(
                    endpoint_id=endpoint_id,
                    resource=resource_type,
                    path=path,
                    name=name
                )
                new_fields.append(field)
            
            db.add_all(new_fields)
            db.flush()
            logger.info(f"All Endpoint field paths are added for endpoint id: {endpoint_id}")
        else:
            logger.warning("No endpoints extracted from fhir sample message")

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

def add_hl7_endpoint_fields(endpoint_id: int, sample_msg: str,  db: Session) -> bool: # uses the old session
    """
    Internal helper: parse an HL7 v2.x sample message, extract field paths per segment,
    map them to canonical names, and persist them as EndpointField records.

    Iterates over each segment (skipping the MSH header), extracts field/component/subcomponent
    paths using HL7 dot-notation (e.g., PID-5.1), and stores matched fields.

    Args:
        endpoint_id (int): The ID of the endpoint to attach discovered fields to.
        sample_msg (str): Raw HL7 v2.x message string with segments separated by newlines.
        db (Session): Active SQLAlchemy database session.

    Returns:
        True on success.

    Raises:
        HTTPException (400): If any error occurs during parsing or DB operations.
    """
    try:
        print(sample_msg)
        for segment in sample_msg.split('\n')[1:]:
            if segment[0:3].strip() == "":
                logger.error(f"segment not valid: {segment}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"segment not valid: {segment}")
            
            segment_type, paths = hl7_extract_paths(segment)
            endpoint_fields = {}
            for path in paths:
                if path in canonical_paths:
                    name = canonical_paths[path]
                    endpoint_fields[name] = path
                    logger.info(f"Mapped field {name} to path {path}")
                else:
                    logger.warning(f"No canonical mapping found for path {path}, skipping.")
            
            new_fields = []
            for name, path in endpoint_fields.items():
                field = models.EndpointFileds(
                    endpoint_id=endpoint_id,
                    resource=segment_type,
                    path=path,
                    name=name
                )
                new_fields.append(field)
            db.add_all(new_fields)
            db.flush()
        return True

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

