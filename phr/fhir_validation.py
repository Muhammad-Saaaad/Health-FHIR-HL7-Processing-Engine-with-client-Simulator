import re

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
