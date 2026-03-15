from fhir.resources.patient import Patient
from fhir.resources.humanname import HumanName

patient = Patient()

test = {
  "resourceType": "Bundle",
  "type": "message",
  "entry": [
      {
        "resource": {
            "resourceType": "Patient",
            "identifier": [{ "value": "23" }],
            "name": [{ "family": "saad", "given": [] }],
            "gender": "Male",
            "birthDate": "2004-10-06",
            "address": [{ "text": "123 street, city, country" }],
            "telecom" : [{
                "value": "+33 (237) 998327"
                }] 
        }
      }
  ]
}


# patient.name = [HumanName(given=["Muhammad"], family="Saad")]
# patient.gender = "Male"

# # print(patient.json()) # type is str
# # print(patient.model_dump()) # type is dict

# try:
#     test_patient = Patient.model_validate(test)
#     print(f"validation Completed: {test_patient.model_dump()}")
# except Exception as e:
#     print(f"Validation Failed: {str(e)}")

############################################################

from fhir.resources import get_fhir_model_class
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
        resource_instance = resource_class(**fhir_data)
        # print(resource_instance)
        
        return True, f"Success: {resource_type} is valid."

    except KeyError:
        return False, f"Error: '{resource_type}' is not a recognized FHIR resource."
    except ValidationError as e:
        # Returns a detailed list of what failed validation
        return False, f"Validation Failed: {e.json(indent=2)}"
    except Exception as e:
        return False, f"Unexpected Error: {str(e)}"

# Usage Example:
incoming_msg = {
    "resourceType": "Patient",
    "id": "example",
    "active": True,
    "name": [{"family": "Doe", "given": ["John"]}]
}

is_valid, message = validate_unknown_fhir_resource(incoming_msg)
print(message)
