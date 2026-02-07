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
    try:

        if not db.get(models.Server, server_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"server id {server_id} does not exists")

        data = db.query(models.Endpoints).filter(models.Endpoints.server_id == server_id).all()
        return data

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))

@router.post("/add-endpoint", status_code=status.HTTP_201_CREATED)
def add_endpoint(endpoint: AddEndpoint, db: Session = Depends(get_db)):
    try:
        if not db.get(models.Server, endpoint.server_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Server does not exist")

        if db.query(models.Endpoints).filter(models.Endpoints.server_id == endpoint.server_id, 
                                             models.Endpoints.url == endpoint.url).first():
            
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL already exists")

        new_endpoint = models.Endpoints(
            server_id=endpoint.server_id,
            url=endpoint.url,
        )
        db.add(new_endpoint)
        db.flush()
        db.refresh(new_endpoint)

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
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")
    
def add_fhir_endpoint_fields(endpoint_id: int, sample_msg: str,  db: Session): # uses the old session
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

def fhir_extract_paths(data, prefix=""):
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



def get_value_by_path(obj, path): # give the entire fhir msg and it will extract the value at that path
    
    # Split path by dots and brackets [ ]
    # "name[0].family" -> ["name", "0", "", "family"]
    #  "text" -> ["text"]
    keys = re.split(r'\.|\[|\]', path)
    print(keys)
    keys = [k for k in keys if k]  # Remove empty strings
    
    current = obj
    
    for key in keys:
        if key.isdigit():  # Array index
            current = current[int(key)]
        else:  # Object key
            current = current.get(key) if isinstance(current, dict) else None
            
        if current is None:
            return None
            
    return current