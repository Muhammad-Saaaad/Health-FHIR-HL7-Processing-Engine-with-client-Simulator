import re

def hl7_extract_paths(segment):
    """
    Parse a single HL7 segment string and return all field/component/subcomponent paths.

    Generates dot-notation paths such as:
    - `PID-3` (simple field)
    - `PID-5.1` (component within a field, split by `^`)
    - `PID-5.1.2` (subcomponent within a component, split by `&`)

    Args:
        segment (str): A single HL7 segment string (e.g., "PID|1||12345^^^MR||Smith^John").

    Returns:
        tuple: (segment_type: str, paths: list[str])
            - `segment_type`: The segment identifier (e.g., "PID", "IN1").
            - `paths`: List of all non-empty field paths found in the segment.
    """
    paths = []
    fields = segment.split('|')
    segment_type = fields[0]  # PID, IN1, etc.
    for i, field in enumerate(fields[1:], start=1):
        if field == '':
            continue
        if '^' in field:
            components = field.split('^')
            for j, component in enumerate(components, start=1):
                if '&' in component:
                    subcomponents = component.split('&')
                    for k, subcomponent in enumerate(subcomponents, start=1):
                        paths.append(f"{segment_type}-{i}.{j}.{k}")
                else:
                    paths.append(f"{segment_type}-{i}.{j}")
        else:
            paths.append(f"{segment_type}-{i}")
    return (segment_type, paths)


def get_hl7_value_by_path(hl7_message, paths):
    """
    Extract field values from a full HL7 message for a given list of dot-notation paths.

    Iterates over all segments in the message and resolves each path, handling field-level,
    component-level (`^`), and subcomponent-level (`&`) access with bounds checking.

    Args:
        hl7_message (str): Full HL7 v2.x message string with segments separated by newlines.
        paths (list[str]): List of paths to extract (e.g., ["PID-3", "PID-5.1", "IN1-3"]).

    Returns:
        dict: A mapping of path -> extracted value (e.g., {"PID-3": "12345", "PID-5.1": "Smith"}).
              Paths with no data at their location return an empty string.
    """
    segments = hl7_message.split('\n')[1:]
    value = {}
    for segment in segments:
        for path in paths:
            sp_path = re.split(r"-|\.", path)  # [PID, 5, 2, 1]
            fields = segment.split("|")

            if fields[0] == sp_path[0]:
                field_val = fields[int(sp_path[1])] if int(sp_path[1]) < len(fields) else ''

                if "^" in field_val and len(sp_path) > 2:
                    components = field_val.split("^")
                    comp = components[int(sp_path[2]) - 1] if int(sp_path[2]) - 1 < len(components) else ''
                    if "&" in comp and len(sp_path) > 3:
                        sub_components = comp.split("&")
                        value[path] = sub_components[int(sp_path[3]) - 1] if int(sp_path[3]) - 1 < len(sub_components) else ''
                    else:
                        value[path] = comp
                else:
                    value[path] = field_val
    return value