import re 

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
            current = current[int(key)]
        else:  # Object key
            current = current.get(key) if isinstance(current, dict) else None
            
        if current is None:
            return None
            
    return current