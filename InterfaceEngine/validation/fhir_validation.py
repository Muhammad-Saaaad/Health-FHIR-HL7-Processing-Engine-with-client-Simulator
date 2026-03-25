import re

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
        print(resource_type)
        
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
        path (str): Dot/bracket notation path string (e.g., `"name[0].family"`, `"gender"`).

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
            current = current[int(key)]
        else:  # Object key
            current = current.get(key) if isinstance(current, dict) else None
            
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


def build_fhir_message(output_data: dict[str, str],
                       dest_path_to_resource: dict[str, str]) -> dict:
    """
    Reconstruct a proper FHIR JSON object (or Bundle) from a flat
    {dest_path: value} mapping produced by the route worker.

    Each dest_path has the form "ResourceType-dot.bracket[0].path".
    If multiple resource types are present a FHIR Bundle is returned;
    otherwise a single resource object is returned.

    Args:
        output_data          : {full_prefixed_path: value}
        dest_path_to_resource: {full_prefixed_path: resource_type}

    Returns:
        FHIR-compliant dict (single resource or Bundle).
    """
    # Group paths by resource type
    resources: dict[str, dict] = {}

    for path, value in output_data.items():
        resource_type = dest_path_to_resource.get(path)
        if not resource_type: # if no resource_type then continue to the next resource
            continue

        if resource_type not in resources: # if the resource is not present then only make a resource.
            resources[resource_type] = {"resourceType": resource_type}

        # Strip "ResourceType-" prefix, then tokenise
        suffix = path.split("-", 1)[1] if "-" in path else path # the 1 in the .split() means that max_split = 1

        # Split path by dots and brackets [ ]
        # "name[0].family" -> ["name", "0", "", "family"]
        #  "gender" -> ["gender"]
        keys = [k for k in re.split(r"\[|\]|\.", suffix) if k]
        _set_nested(resources[resource_type], keys, value)

    # Single resource — return it directly
    if len(resources) == 1:
        return next(iter(resources.values()))

    # Multiple resources — wrap in a Bundle
    return {
        "resourceType": "Bundle",
        "type": "message",
        "entry": [
            {
                "resource": res,
            }
            for res in resources.values()
        ],
    }

# async def build_fhir_json(output_data, dest_path_to_resource):
#     resources = {}

#     for path, value in output_data.items():
#         resource = dest_path_to_resource[path]

#         resources.setdefault(resource, {})
#         resources[resource][path] = value
    
#     return resources

if __name__ == "__main__":
    # Usage Example:

    patient_registration = {
        "resourceType": "Bundle",
        "type": "message",
        "entry": [
            { 
                "resource": {
                    "resourceType": "Patient",
                    "identifier": [
                        { "type": { "coding": [{ "code": "MR" }]}, "value": "23" },
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

    encounter = {
        "resourceType": "Encounter",
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
        # 4. CONSULTATION NOTES
        "extension": [{
                "url": "http://example.org/fhir/StructureDefinition/encounter-consultation-notes",
                "valueString": "Patient responded well to medication. Follow-up advised in 2 weeks."
            }
        ]
    }

    is_valid, message = validate_unknown_fhir_resource(patient_registration)
    print(message)