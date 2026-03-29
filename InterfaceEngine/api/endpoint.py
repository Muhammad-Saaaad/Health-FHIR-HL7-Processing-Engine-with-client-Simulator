import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, HTTPException, Depends, Response, Request
from sqlalchemy.orm import Session

from schemas.endpoint import AddEndpoint
import models
from database import get_db
from rate_limiting import limiter
from validation.mappings import FHIR_EXACT_CANONICAL, FHIR_PATTERN_CANONICAL, HL7_EXACT_CANONICAL
from validation.fhir_validation import validate_unknown_fhir_resource, fhir_extract_paths
from validation.hl7_validation import hl7_extract_paths

router = APIRouter(tags=["Endpoint"])

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

@router.get("/server-endpoint/{server_id}", status_code=status.HTTP_200_OK)
@limiter.limit("40/minute")  # Limit to 40 requests per minute per IP
def server_endpoint(server_id: int, request: Request, response: Response, db:Session = Depends(get_db)):
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
        logger.warning(f"Server endpoint list rejected: server id {server_id} does not exist")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"server id {server_id} does not exists")
    try:
        data = db.query(models.Endpoints).filter(models.Endpoints.server_id == server_id).all()
        return data

    except Exception as exp:
        logger.error(f"Server endpoint list failed for server_id={server_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.post("/add-endpoint", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")  # Limit to 10 requests per minute per IP
async def add_endpoint(endpoint: AddEndpoint, request: Request, response: Response, db: Session = Depends(get_db)):
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
    logger.info(
        f"Add endpoint request received: server_id={endpoint.server_id}, url={endpoint.url}, "
        f"server_protocol={endpoint.server_protocol}"
    )

    if not db.get(models.Server, endpoint.server_id):
        logger.warning(f"Add endpoint rejected: server id {endpoint.server_id} does not exist")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server does not exist")

    if db.query(models.Endpoints).filter(models.Endpoints.server_id == endpoint.server_id, 
                                            models.Endpoints.url == endpoint.url).first():
        logger.warning(
            f"Add endpoint rejected: duplicate URL for server_id={endpoint.server_id}, url={endpoint.url}"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="URL already exists")
    
    if endpoint.sample_msg in [None, "", {}]:
        logger.warning("Add endpoint rejected: sample message is missing")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Sample message is required to extract endpoint fields")

    if endpoint.server_protocol not in ["FHIR", "HL7"]:
        logger.warning(f"Add endpoint rejected: unsupported server protocol '{endpoint.server_protocol}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Server Protocol is not FHIR or HL7")

    try:
        new_endpoint = models.Endpoints(
            server_id=endpoint.server_id,
            url=endpoint.url,
        )
        db.add(new_endpoint)
        db.flush()
        logger.info(f"Endpoint created and flushed successfully: endpoint_id={new_endpoint.endpoint_id}")

        if endpoint.server_protocol == "FHIR":
            sample_msg = endpoint.sample_msg
            is_valid, message = validate_unknown_fhir_resource(sample_msg)
            if not is_valid:
                logger.error(f"Invalid FHIR sample message: {message}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
            
            add_fhir_endpoint_fields(
                endpoint_id=new_endpoint.endpoint_id,
                sample_msg=sample_msg, db=db
            )
            logger.info(f"FHIR endpoint fields added successfully for endpoint_id={new_endpoint.endpoint_id}")
        else: # if not FHIR then it should be HL7
            add_hl7_endpoint_fields(
                endpoint_id=new_endpoint.endpoint_id,
                sample_msg=endpoint.sample_msg.strip(), db=db
            )
            logger.info(f"HL7 endpoint fields added successfully for endpoint_id={new_endpoint.endpoint_id}")
        db.commit()
        return {"message": "Endpoint added successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Add endpoint failed for url={endpoint.url}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")


@router.get("/endpoint_field_path/{endpoint_id}", status_code=status.HTTP_200_OK)
@limiter.limit("40/minute")  # Limit to 40 requests per minute per IP
def endpoint_field_paths(endpoint_id: int, request: Request, response: Response, db:Session = Depends(get_db)):
    """
    Retrieve all discovered fields for a specific endpoint.

    This is used when configuring a new route — you call this endpoint for both the source
    and destination endpoint to get the list of available fields, then use those field IDs
    in the route's mapping rules.

    **Path Parameters:**
    - `endpoint_id` (int, required): The unique ID of the endpoint whose fields to retrieve.

    **Response (200 OK):**
    Returns a list of endpoint field objects. Each item includes:
    - `endpoint_field_id`: Unique field identifier (used as `src_paths` / `dest_paths` in route rules)
    - `endpoint_id`: The parent endpoint's ID
    - `resource`: The FHIR resource type or HL7 segment (e.g., "Patient", "PID")
    - `path`: The field path in dot/bracket notation (e.g., "name[0].text", "PID-5.1")
    - `name`: The canonical human-readable field name (e.g., "fullname", "mpi")

    **Error Responses:**
    - `404 Not Found`: No endpoint exists with the given `endpoint_id`
    - `400 Bad Request`: Unexpected database error
    """
    if not db.get(models.Endpoints, endpoint_id):
        logger.warning(f"Endpoint field paths rejected: endpoint id {endpoint_id} does not exist")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"endpoint id {endpoint_id} does not exists")

    try:    
        data = db.query(models.EndpointFields).filter(models.EndpointFields.endpoint_id == endpoint_id).all()
        return data

    except Exception as exp:
        logger.error(f"Endpoint field paths failed for endpoint_id={endpoint_id}: {str(exp)}")
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
        logger.info(f"FHIR field extraction started for endpoint_id={endpoint_id}")
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
                paths.extend([f"{resource_type}-{p}" for p in raw_paths]
        )
        if len(paths) > 0:
            endpoint_fields = {}
            for path in paths:

                name = resolve_canonical_name(full_path=path)
                if not name:
                    continue
                endpoint_fields[name] = path
                logger.info(f"Mapped field {name} to path {path}")
            
            new_fields = []
            for name, path in endpoint_fields.items():
                field = models.EndpointFields(
                    endpoint_id=endpoint_id,
                    resource=path.split("-")[0].strip(), # resource type is the prefix before the first dash
                    path=path,
                    name=name
                )
                new_fields.append(field)
            
            db.add_all(new_fields)
            db.flush()
            logger.info(
                f"FHIR field extraction completed for endpoint_id={endpoint_id}, total_fields_added={len(new_fields)}"
            )
        else:
            logger.warning(f"No endpoint fields extracted from FHIR sample for endpoint_id={endpoint_id}")

    except Exception as e:
        logger.error(f"FHIR field extraction failed for endpoint_id={endpoint_id}: {str(e)}")
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
        logger.info(f"HL7 field extraction started for endpoint_id={endpoint_id}")
        total_fields_added = 0
        for segment in sample_msg.split('\n')[1:]:
            if segment[0:3].strip() == "":
                logger.error(f"segment not valid: {segment}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"segment not valid: {segment}")
            
            segment_type, paths = hl7_extract_paths(segment)
            endpoint_fields = {}
            for path in paths:
                    
                name = resolve_canonical_name(full_path=path)
                if not name:
                    continue
                endpoint_fields[name] = path
                logger.info(f"Mapped field {name} to path {path}")
               
            new_fields = []
            for name, path in endpoint_fields.items():
                field = models.EndpointFields(
                    endpoint_id=endpoint_id,
                    resource=segment_type,
                    path=path,
                    name=name
                )
                new_fields.append(field)
            total_fields_added += len(new_fields)
            db.add_all(new_fields)
            db.flush()
        logger.info(
            f"HL7 field extraction completed for endpoint_id={endpoint_id}, total_fields_added={total_fields_added}"
        )
        return True

    except Exception as e:
        logger.error(f"HL7 field extraction failed for endpoint_id={endpoint_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def resolve_canonical_name(full_path: str) -> str | None:
    """
    Resolve a full prefixed path to a canonical name using two layers:

    Layer 1 — Exact match in FHIR_EXACT_CANONICAL or HL7_EXACT_CANONICAL.
    Layer 2 — Suffix pattern match in FHIR_PATTERN_CANONICAL (FHIR only).

    Args:
        full_path: e.g. "Patient-name[0].family"  or  "PID-5.1"

    Returns:
        Canonical name string, or None if no mapping found.
    """
    # ── Layer 1: exact match ─────────────────────────────────────────────────
    if full_path in FHIR_EXACT_CANONICAL:
        return FHIR_EXACT_CANONICAL[full_path]

    if full_path in HL7_EXACT_CANONICAL:
        return HL7_EXACT_CANONICAL[full_path]

    # ── Layer 2: FHIR suffix pattern ─────────────────────────────────────────
    if "-" in full_path:
        resource_type, suffix = full_path.split("-", 1)
        for pattern, name_template in FHIR_PATTERN_CANONICAL:
            if suffix == pattern:
                return name_template.replace("{resource}", resource_type.lower())

    logger.warning(f"No canonical mapping found for path {full_path}, skipping.")
    return None  # truly unknown — caller decides whether to skip or store raw
