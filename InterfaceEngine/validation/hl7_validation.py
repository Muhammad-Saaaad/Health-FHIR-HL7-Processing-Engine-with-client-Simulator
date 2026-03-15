import re

def hl7_extract_paths(segment) -> list:
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
    segment_type = fields[0].strip() # PID etc.
    for i , field in enumerate(fields[1:], start=1):
        if not field:
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
    normalised = hl7_message.replace("\r", "\n")
    segments = [s for s in normalised.split("\n") if s.strip()]
    if segments and segments[0].startswith("MSH"):
        segments = segments[1:]
        
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
