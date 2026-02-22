import re
import logging

from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from schemas.endpoint import AddEndpoint
import models
from database import get_db

router = APIRouter(tags=["Endpoint"])
logging.basicConfig(
    level=logging.INFO,
    filename="mapping.log",
    format="%(asctime)s - %(levelname)s - %(message)s"
)

canonical_paths = {
    "identifier[0].value": "mpi",
    "name[0].text": "fullname",
    "name[0].given": "given name",
    "name[0].family[0]": "family name",
    "gender": "gender",
    "birthDate": "birth date",
    "telecom[0].value": "phone number",
    "address[0].text": "address",
    
    "PID-3": "mpi",
    "PID-5": "fullname",
    "PID-5.1": "family name",
    "PID-5.2": "given name",
    "PID-7": "birth date",
    "PID-8": "gender",
    "PID-11": "address",
    "PID-13": "phone number"
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Server does not exist")

    if db.query(models.Endpoints).filter(models.Endpoints.server_id == endpoint.server_id, 
                                            models.Endpoints.url == endpoint.url).first():
        
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL already exists")

    try:
        new_endpoint = models.Endpoints(
            server_id=endpoint.server_id,
            url=endpoint.url,
        )
        db.add(new_endpoint)
        db.flush()
        db.refresh(new_endpoint)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

    if endpoint.server_protocol == "FHIR":
        if add_fhir_endpoint_fields(endpoint_id=new_endpoint.endpoint_id, sample_msg=endpoint.sample_msg, db=db):
            db.commit()
        else:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to add endpoint FHIR fields from sample message")
        
    elif endpoint.server_protocol == "HL7":
        if add_hl7_endpoint_fields(endpoint_id=new_endpoint.endpoint_id, sample_msg=endpoint.sample_msg, db=db):
            db.commit()
        else:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to add endpoint HL7 fields from sample message")
        return {"message": "Endpoint added successfully"}
    
def add_fhir_endpoint_fields(endpoint_id: int, sample_msg: str,  db: Session): # uses the old session
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
        global canonical_paths

        print(sample_msg)
        if sample_msg['resourceType'] != 'Bundle': 
            resource_type = sample_msg['resourceType']
            paths = fhir_extract_paths(sample_msg)

            endpoint_fields = {}
            for path in paths:

                if path in canonical_paths:
                    name = canonical_paths[path]
                    endpoint_fields[name] = path
                    logging.info(f"Mapped field {name} to path {path}")
                else:
                    logging.warning(f"No canonical mapping found for path {path}, skipping.")
            
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

        else:
            for entry in sample_msg['entry']:
                resource_type = entry['resource']['resourceType']
                paths = fhir_extract_paths(entry['resource'])

                endpoint_fields = {}
                for path in paths:

                    if path in canonical_paths:
                        name = canonical_paths[path]
                        endpoint_fields[name] = path
                        logging.info(f"Mapped field {name} to path {path}")
                    else:
                        logging.warning(f"No canonical mapping found for path {path}, skipping.")
                
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
        
        return True

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

def add_hl7_endpoint_fields(endpoint_id: int, sample_msg: str,  db: Session): # uses the old session
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
        global canonical_paths

        print(sample_msg)
        for segment in sample_msg.split('\n')[1:]:
            segment_type, paths = hl7_extract_paths(segment)
            endpoint_fields = {}
            for path in paths:
                if path in canonical_paths:
                    name = canonical_paths[path]
                    endpoint_fields[name] = path
                    logging.info(f"Mapped field {name} to path {path}")
                else:
                    logging.warning(f"No canonical mapping found for path {path}, skipping.")
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


def hl7_extract_paths(segment):
    """
    Parse a single HL7 segment string and return all field/component/subcomponent paths.

    Generates dot-notation paths such as:
    - `PID-3` (simple field)
    - `PID-5.1` (component within a field)
    - `PID-5.1.2` (subcomponent within a component)

    Args:
        segment (str): A single HL7 segment string (e.g., "PID|1||12345^^^MR||Smith^John^A").

    Returns:
        tuple: (segment_type: str, paths: list[str])
            - `segment_type`: e.g., "PID", "MSH"
            - `paths`: list of dot-notation path strings for all non-empty fields
    """
    paths = []

    # for segment in segments[1:]
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

def fhir_extract_paths(data, prefix=""):
    """
    Recursively traverse a FHIR JSON object and return all leaf-node paths in dot/bracket notation.

    Generates paths such as:
    - `"gender"` (simple scalar field)
    - `"name[0].text"` (field inside a list item)
    - `"name[0].given"` (list of strings — stored as the list path itself)

    Args:
        data (dict | list | scalar): The FHIR JSON object or sub-object to traverse.
        prefix (str): The current accumulated path (used during recursion). Leave empty on first call.

    Returns:
        list[str]: All discovered leaf-level paths within the data structure.
    """
    paths = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'resourceType':
                continue
            new_prefix = f"{prefix}.{key}" if prefix else key
            paths.extend(fhir_extract_paths(value, new_prefix))

    elif isinstance(data, list):
        if len(data) > 0:
            # if the all the items in the list are strings and length >1 then it means the data is like this ["saad", "ali"]
            # so we add the just the entire list there
            if all(isinstance(item, str) for item in data) and len(data) >1:
                paths.append(prefix)
            else:
                for i, item in enumerate(data):
                    paths.extend(fhir_extract_paths(item, f"{prefix}[{i}]"))

    else:
        paths.append(prefix)

    return paths

def get_hl7_value_by_path(hl7_message, paths): 
    """
    Extract values from an HL7 message for a given list of dot-notation field paths.

    Iterates over all segments in the message and resolves each path. Handles field-level,
    component-level (`^`), and subcomponent-level (`&`) access.

    Args:
        hl7_message (str): Full HL7 v2.x message string with segments separated by newlines.
        paths (list[str]): List of paths to extract (e.g., ["PID-3", "PID-5.1"]).

    Returns:
        dict: A mapping of path -> extracted value (e.g., {"PID-3": "12345", "PID-5.1": "Smith"}).
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

def get_fhir_value_by_path(obj, path): # give the entire fhir msg and it will extract the value at that path
    """
    Extract a single value from a FHIR JSON object using a dot/bracket notation path.

    Traverses the object step by step, handling both dict keys and list indices.

    Args:
        obj (dict): The root FHIR JSON object to traverse.
        path (str): Dot/bracket notation path string (e.g., `"name[0].family"`, `"gender"`).

    Returns:
        The value at the specified path, or `None` if any key/index along the path is missing.

    Example:
        >>> get_fhir_value_by_path(fhir_patient, "name[0].text")
        "John Smith"
    """
    # Split path by dots and brackets [ ]
    # "name[0].family" -> ["name", "0", "", "family"]
    #  "gender" -> ["gender"]
    keys = re.split(r'\.|\\[|\\]', path)
    keys = [k for k in keys if k]  # Remove empty strings
    
    current = obj
    
    for key in keys: 
        # Checks if the current is a dictionary, if yes then take the key else take none. 
        # checks if the key is a digit if yes, then it's means that the current is a list
        #    and we take the index of it, that is the key in this case
        if key.isdigit():  # Array index
            current = current[int(key)]
        else:  # Object key
            current = current.get(key) if isinstance(current, dict) else None
            
        if current is None:
            return None
            
    return current