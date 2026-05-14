import json
import re
from uuid import uuid4  

from fhir.resources.R4B import get_fhir_model_class
from pydantic import ValidationError

def validate_unknown_fhir_resource(fhir_data: dict): # validation of any fhir message
    # 1. Identify the resource type
    
    resource_type = fhir_data.get("resourceType")
    if not resource_type:
        return False, "Error: JSON is missing 'resourceType' field."

    try:
        # 2. Dynamically fetch the model class
        resource_class = get_fhir_model_class(resource_type)
        
        # 3. Instantiate to trigger validation
        # If the data doesn't match the FHIR spec, a ValidationError is raised
        resource_class(**fhir_data)
        # print(resource_type)
        
        return True, f"Success: {resource_type} is valid."

    except KeyError:
        return False, f"Error: '{resource_type}' is not a recognized FHIR resource."
    except ValidationError as e:
        # Returns a detailed list of what failed validation
        return False, f"Validation Failed: {str(e)}"
    except Exception as e:
        return False, f"Unexpected Error: {str(e)}"

def fhir_extract_paths(data, prefix="") -> list:
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

def get_fhir_value_by_path(obj, path): # give the entire fhir msg and it will extract the value at that path
    """
    Extract a single value from a FHIR JSON object using a dot/bracket notation path.

    Traverses the object step by step, handling both dict keys and list indices.

    Args:
        obj (dict): The root FHIR JSON object to traverse.
        path (str): Dot/bracket notation path string (e.g., `"Patient[1]-name[0].family"`, `"gender"`).

    Returns:
        The value at the specified path, or `None` if any key/index along the path is missing.

    Example:
        >>> get_fhir_value_by_path(fhir_patient, "name[0].text")
        "John Smith"
    """
    # Strip the resource-type prefix before traversal.
    # e.g. "Patient-name[0].text" → "name[0].text"
    if "-" in path:
        path = path.split("-", 1)[1]

    # Split path by dots and brackets [ ]
    # "name[0].family" -> ["name", "0", "", "family"]
    #  "gender" -> ["gender"]
    keys = re.split(r'\.|\[|\]', path)
    keys = [k for k in keys if k]  # Remove empty strings
    
    current = obj
    
    for key in keys: 
        # Checks if the current is a dictionary, if yes then take the key else take none. 
        # checks if the key is a digit if yes, then it's means that the current is a list
        #    and we take the index of it, that is the key in this case
        if key.isdigit():  # Array index
            if not isinstance(current, list):
                return None
            idx = int(key)
            if idx >= len(current):
                return None
            current = current[idx]
        else:  # Object key
            if not isinstance(current, dict):
                return None
            current = current.get(key)

        if current is None:
            return None
            
    return current

def _set_nested(obj: dict, keys: list, value) -> None:
    """
    Recursively create nested dicts/lists and set value at the leaf.
    input data: 
        obj -> Patient
        keys -> ["name", "0", "", "family"]
        value -> Saad

    """
    key = keys[0]

    if len(keys) == 1:
        if key.isdigit():
            # obj is actually a list — caller should handle list growth
            pass
        else:
            obj[key] = value
        return

    next_key = keys[1]

    if key.isdigit():
        return  # handled by parent

    # Determine what container the next level needs
    if next_key.isdigit():
        # Next level is a list index
        idx = int(next_key)
        if key not in obj or not isinstance(obj[key], list):
            obj[key] = []
        lst = obj[key]
        while len(lst) <= idx:
            lst.append({})
        _set_nested(lst[idx], keys[2:], value)
    else:
        if key not in obj or not isinstance(obj[key], dict):
            obj[key] = {}
        _set_nested(obj[key], keys[1:], value)


async def build_fhir_message(output_data: dict[str, str],
                       dest_path_to_resource: dict[str, str]) -> dict:
    """
    Reconstruct a proper FHIR JSON object (or Bundle) from a flat
    {dest_path: value} mapping produced by the route worker.

    Each dest_path has the form "ResourceType-dot.bracket[0].path".
    Repeated resources are supported using an indexed resource prefix,
    e.g. "Observation[1]-status" and "Observation[2]-status".
    If multiple resource types are present a FHIR Bundle is returned;
    otherwise a single resource object is returned.

    Args:
        output_data          : {full_prefixed_path: value}
        dest_path_to_resource: {full_prefixed_path: resource_type}

    Returns:
        FHIR-compliant dict (single resource or Bundle).
    """
    # Group paths by resource type + occurrence index.
    # Key shape: ("Patient", 1), ("Patient", 2), ("Coverage", 1), ...
    resources: dict[tuple[str, int], dict] = {}
    resource_order: list[tuple[str, int]] = []

    for path, value in output_data.items():

        if "-" in path:
            prefix, suffix = path.split("-", 1)
        else:
            prefix, suffix = path, path

        # Prefix can be "Patient" or "Patient[2]".
        prefix_match = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)(?:\[(\d+)\])?", prefix)
        parsed_resource_type = prefix_match.group(1) if prefix_match else None
        occurrence = int(prefix_match.group(2)) if prefix_match and prefix_match.group(2) else 1

        resource_type = dest_path_to_resource.get(path) or parsed_resource_type
        if not resource_type: # if no resource_type then continue to the next resource
            continue

        resource_key = (resource_type, occurrence)
        if resource_key not in resources: # if this resource occurrence is not present then create it.
            resources[resource_key] = {"resourceType": resource_type}
            resource_order.append(resource_key)

        # Strip "ResourceType-" prefix, then tokenise.
        # Works for both "Patient-name[0].text" and "Patient[2]-name[0].text".

        # Split path by dots and brackets [ ]
        # "name[0].family" -> ["name", "0", "", "family"]
        #  "gender" -> ["gender"]
        keys = [k for k in re.split(r"\[|\]|\.", suffix) if k]
        _set_nested(resources[resource_key], keys, value)

    # Single resource — return it directly
    if len(resources) == 1:
        return next(iter(resources.values()))

    # Multiple resources — wrap in a Bundle
    return {
        "resourceType": "Bundle",
        "id": str(uuid4()), 
        "type": "message",
        "entry": [
            {
                "resource": res,
            }
            for key in resource_order
            for res in [resources[key]]
        ],
    }

if __name__ == "__main__":
    # Usage Example:

    from uuid import uuid4
    unique_id = str(uuid4())
    # print("unique_id --> ", unique_id)

    patient_registration = {
        "resourceType": "Bundle",
        "type": "message",
        "id": unique_id,
        "entry": [
            { 
                "resource": {
                    "resourceType": "Patient",
                    "id": unique_id,
                    "identifier": [
                        { "type": { "coding": [{ "code": "NI" }]}, "value": "37201-23123123"}
                    ],
                    "name": [{ "text": "Muhammad Saad" }],
                    "gender": "male",
                    "birthDate": "2004-10-06",
                    "address": [{ "text": "123 street, city, country" }],
                    "telecom" : [{
                        "value" : "+33 (237) 998327"
                    }]
                }
            },
            {
                "resource": {
                    "resourceType": "Coverage",
                    "id": unique_id,
                    "identifier": [
                        {
                            "value": "3"  # plan id.
                        }   
                    ],
                    "status": "active",
                    "class": [
                        {
                            "type": { "coding": [{"code": "plan"}] },
                            "value": "Gold",
                        }
                    ],
                    "beneficiary": {
                        "reference": "23" # patient mpi
                    },
                    "subscriberId": "21", # policy number
                    "payor": [
                        {
                            "reference": "Organization/insurance-company-001" # insurance company id
                        }
                    ]
                }
            }
        ]
    }

    patient_visit = {
        "resourceType": "Bundle",
        "type": "message",
        "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
        "entry": [
            {
                "resource": {
                    "resourceType": "Practitioner",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "identifier" :[ {"value": "PRAC-001"} ],
                    "name": [{"text": "Dr. Ayesha Khan"}],
                    "telecom": [{"value": "+33 (237) 998327"}],
                    "extension": [{
                        "valueString": "General Practitioner with 10 years of experience in primary care, specializing in patient-centered treatment and preventive medicine."
                    }]
                }
            },
            {
                "resource": {
                    "resourceType": "PractitionerRole",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "specialty": [ { "coding": [{"display": "General Practitioner"}] } ],
                    "practitioner": {"reference": f"Practitioner/PRAC-001"},
                    "organization": {"display": "Shifa International"}
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "identifier": [
                        {
                            "value": "VID-2024-12345"  # Primary key from EHR - send to PHR
                        }
                    ],
                    "status": "in-progress",
                    "class": {
                        "code": "AMB"  # AMB=Ambulatory, IMP=Inpatient, EMER=Emergency, VR=Virtual
                    },
                    # 1. ENCOUNTER TITLE
                    "type": [
                        {
                            "text": "General Consultation"
                        }
                    ],
                    # 2. PATIENT COMPLAINT
                    "reasonCode": [
                        {
                            "text": "Patient experiencing severe headache and dizziness"
                        }
                    ],
                    # 3. DIAGNOSIS - display field shows the disease name (no separate Condition resource needed)
                    "diagnosis": [
                        {
                            "condition": {
                                "display": "Migraine"  # display shows the disease name
                            }
                        }
                    ],
                    "subject": {"reference": "Patient/32"}, # reference to the patient resource (with mpi = 32 in this case)
                    # 4. CONSULTATION NOTES
                    "extension": [{
                            "valueString": "Patient responded well to medication. Follow-up advised in 2 weeks."
                        }
                    ]
                }
            },
            {
                "resource": {
                    "resourceType": "Invoice",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "status": "issued",
                    "subject": {"reference": "Patient/32"},
                    "participant": [{"actor": {"reference": "Practitioner/PRAC-001"}}],
                    "totalNet": {"value": "150.00"} # "currency": "USD", this can also be added.
                }
            },
            {
                "resource": {
                    "resourceType": "ServiceRequest",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "status": "active",
                    "intent": "order",
                    "code":{
                        "coding": [
                            {
                                # "system": "http://loinc.org",
                                "code": "73761001",
                                "display": "Headache (disorder)"
                            }
                        ]
                    },
                    "subject": {"reference": "Patient/32"},
                    "performer": [{"identifier": {"value": "PRAC-001"}, "display": "IDC"}]
                }
            }
        ]
    }

    Submit_claim = { 
    "resourceType": "Claim",
        "id": "claim-example-01",
        "status": "active",
        "type": {
            "coding": [
                {
                    "display": "Service_LabTest"
                }   
            ]
        },
        "use": "claim",
        "patient": {
            "reference": "Patient/23"
        },
        "created": "2026-02-03T12:00:00Z",
        "provider": {
            "reference":  "Encounter/123"
        },
        "priority": {
            "coding": [
                {
                    "code": "normal"
                }
            ]
        },
        "insurance": [
            {
                "sequence": 1,
                "focal": True,
                "coverage": {
                    "display": "Payer Health Insurance"
                }
            }
        ],
        "total": {
            "value": 150.00,
        }
    }

    response_claim = {
        "resourceType": "ClaimResponse",
        "id": "res-123", 
        "status": "active",
        "type": { "coding": [{"code": "professional"}] },
        "use": "claim",
        "patient": {
            "reference": "patient/1232" 
        },
        "request": {
            "reference": "Encounter/123"
        },
        "created": "2026-05-02T13:23:15Z", 
        "insurer": {
            "display": "Jubilee Insurance"
        },
        "outcome": "complete"
    }
    # ---------------- build_fhir_message test sample ----------------
    # Flat route output -> rebuilt FHIR Bundle with repeated Patient resources
    sample_output_data = {
        "Patient[1]-id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
        "Patient[1]-identifier[0].value": "23",
        "Patient[1]-name[0].text": "Muhammad Saad",
        "Patient[1]-gender": "male",

        "Patient[2]-id": "patient-2-id",
        "Patient[2]-identifier[0].value": "24",
        "Patient[2]-name[0].text": "Ali Khan",
        "Patient[2]-gender": "male",

        "Coverage[1]-id": "coverage-1-id",
        "Coverage[1]-identifier[0].value": "3",
        "Coverage[1]-status": "active",
        "Coverage[1]-beneficiary.reference": "Patient/23",

        "Coverage[2]-id": "coverage-2-id",
        "Coverage[2]-identifier[0].value": "4",
        "Coverage[2]-status": "active",
        "Coverage[2]-beneficiary.reference": "Patient/24",
    }

    sample_dest_path_to_resource = {
        "Patient-id": "Patient",
        "Patient-identifier[0].value": "Patient",
        "Patient-name[0].text": "Patient",
        "Patient-gender": "Patient",
        "Patient-phone": "Patient",
        "Patient-id": "Patient",
        "Patient-identifier[0].value": "Patient",
        "Patient-name[0].text": "Patient",
        "Patient-gender": "Patient",
        "ServiceRequest-id": "ServiceRequest",
        "ServiceRequest-name": "request_name",
        "Coverage-id": "Coverage",
        "Coverage-identifier[0].value": "Coverage",
        "Coverage-status": "Coverage",
        "Coverage-beneficiary.reference": "Coverage",
        "Coverage-id": "Coverage",
        "Coverage-identifier[0].value": "Coverage",
        "Coverage-status": "Coverage",
        "Coverage-beneficiary.reference": "Coverage",
    }
    # import asyncio 

    # rebuilt = asyncio.run(build_fhir_message(sample_output_data, sample_dest_path_to_resource))

    # print("\n--- build_fhir_message sample output ---")
    # print(json.dumps(rebuilt, indent=2))

    is_valid, message = validate_unknown_fhir_resource(patient_registration)
    print(is_valid, " --> \n" ,message)

    # import uuid

    # print(str(uuid.uuid4()))