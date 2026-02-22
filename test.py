test = {
    "resourceType": "Bundle",
    "type": "message",
    "entry": [
        { 
            "resource": {
                "resourceType": "Patient",
                "identifier": [{ "value": "23" }],
                "name": [{ "text": "Muhammad saad" }],
                "gender": "male",
                "birthDate": "2004-10-06",
                "address": [{ "text": "123 street, city, country" }],
                "telecom" : [{"value" : "+33 (237) 998327"}]
            }
        },
        {
            "resource": {
                "resourceType": "Coverage",
                "identifier": [{ "value": 12 }],
                "type": {"text": "Silver"}
            }
        }
    ]
}

test = {
  "resourceType": "Patient",
  "identifier": [{ "value": "23" }],
  "name": [{ "family": ["saad"], "given": [] }],
  "gender": "male",
  "birthDate": "2004-10-06",
  "address": [{ "text": "123 street, city, country" }],
  "telecom" : [{
      "value" : "+33 (237) 998327"
    }]
}


def hl7_extract_paths(segment) -> (str, list[str]):
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

# test = """MSH|^~\\&|EHR||LIS||20260203120000||ADT^A01|MSG00001|P|2.5\nPID|1||23||saad^Muhammad ali||20041006|M|||||
# ORM|2||12||Muhammad^ali||20041006|M|||123 street, city, country||+33 (237) 998327"""
# test = """MSH|^~\\&|LIS||EHR||20260203120000||ADT^A01|MSG00001|P|2.5\nPID|1||23||saad^Muhammad ali||20041006|M|||||
# IN1|1||12||Silver"""
import re

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

# for segment in test.split('\n')[1:]:
#     segment_type, paths = hl7_extract_paths(segment)
#     print(segment_type, paths)
#     print(get_hl7_value_by_path(test, paths))

# def extract_paths(data, prefix=""):
#     paths = []

#     if isinstance(data, dict):
#         for key, value in data.items():
#             if key == 'resourceType':
#                 continue
#             new_prefix = f"{prefix}.{key}" if prefix else key
#             paths.extend(extract_paths(value, new_prefix))

#     elif isinstance(data, list):
#         if len(data) > 0:
#             # if the all the items in the list are strings and length >1 then it means the data is like this ["saad", "ali"]
#             # so we add the just the entire list there
#             if all(isinstance(item, str) for item in data) and len(data) >1:
#                 paths.append(prefix)
#             else:
#                 for i, item in enumerate(data):
#                     paths.extend(extract_paths(item, f"{prefix}[{i}]"))

#     else:
#         paths.append(prefix)

#     return paths

# def get_value_by_path(obj, path): # give the entire fhir msg and it will extract the value at that path
#     import re
#     # Split path by dots and brackets [ ]
#     # "name[0].family" -> ["name", "0", "", "family"]
#     #  "text" -> ["text"]
#     keys = re.split(r'\.|\[|\]', path)
#     print(keys)
#     keys = [k for k in keys if k]  # Remove empty strings
    
#     current = obj
    
#     for key in keys:
#         if key.isdigit():  # Array index
#             current = current[int(key)]
#         else:  # Object key
#             current = current.get(key) if isinstance(current, dict) else None
            
#         if current is None:
#             return None
            
#     return current


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

def get_fhir_value_by_path(obj, path): # give the entire fhir msg and it will extract the value at that path
    
    # Split path by dots and brackets [ ]
    # "name[0].family" -> ["name", "0", "", "family"]
    #  "gender" -> ["gender"]
    keys = re.split(r'\.|\[|\]', path)
    # print(keys)
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

# resource_type = test['resourceType']
# paths = fhir_extract_paths(test)
# print(paths)
# for path in paths:

#     value = get_fhir_value_by_path(test, path)
#     print(path)
#     print(value)

from datetime import datetime

date_with_time = datetime.now()

print(date_with_time.date())