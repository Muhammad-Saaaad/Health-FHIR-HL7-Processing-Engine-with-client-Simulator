from datetime import datetime
import re
from uuid import uuid4

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

                # if "^" in fields[int(sp_path[1])]:
                #     components = fields[int(sp_path[1])].split("^")
                    
                #     if "&" in components[int(sp_path[2])-1]:
                #         sub_components = components[int(sp_path[2])-1].split("&")
                #         value[path] = sub_components[int(sp_path[3])-1]
                #     else:
                #         value[path] = components[int(sp_path[2])-1] 
                # else:
                #     value[path] = fields[int(sp_path[1])]

                if "^" in fields[int(sp_path[1])]:
                    components = fields[int(sp_path[1])].split("^")

                    if len(sp_path) >= 3:  # path requests a component
                        comp = components[int(sp_path[2])-1] if int(sp_path[2])-1 < len(components) else ""

                        if "&" in comp:
                            sub_components = comp.split("&")
                            value[path] = sub_components[int(sp_path[3])-1] if int(sp_path[3])-1 < len(sub_components) else ""
                        else:
                            value[path] = comp
                    else:
                        value[path] = fields[int(sp_path[1])]  # field-level, return raw
                else:
                    value[path] = fields[int(sp_path[1])]
        
    return value

# this output_data contains all the data of the entire hl7 message of every segment,
# with fields and values in a flat structure e.g. {"PID-5.1": "Smith", "PID-3": "12345", "PID-3.4.1": "X"}
def build_hl7_message(output_data: dict[str, str], 
                      src: str,
                      dest: str,
                      msg_type: str) -> str:
    """
    Reconstruct a valid HL7 v2.x message string from a flat
    {dest_path: value} mapping produced by the route worker.

        Handles:
      - Simple fields        PID-3   → PID field 3
      - Component fields     PID-5.1 → PID field 5, component 1 (^ delimiter)
      - Subcomponent fields  PID-3.4.1 → component 4, subcomponent 1 (& delimiter)
            - Repeated segments    OBX[1]-3 and OBX[2]-3 → two OBX lines

    Returns a full HL7 string with MSH prepended and segments separated by \\r\\n.

    Args:
        output_data : {full_prefixed_path: value}  e.g. {"PID-5.1": "Smith"}
        src         : Sending application / facility name
        dest        : Receiving application / facility name
        msg_type    : HL7 message type, e.g. "ADT^A01" or "ORU^R01"

    Returns:
        Complete HL7 message string.
    """
    dt = datetime.now().strftime("%Y%m%d%H%M%S")
    control_id = f"MSG{uuid4()}"

    msh = (
        f"MSH|^~\\&|{src}||{dest}||{dt}||{msg_type}"
        f"|{control_id}|P|2.5"
    )
    
    # ── Build segment buffers ─────────────────────────────────────────────────
    # Structure:
    # {
    #   segment_type: {
    #     occurrence_index: {
    #       field_idx: { comp_idx: { sub_idx: value } }
    #     }
    #   }
    # }
    seg_data: dict[str, dict[int, dict[int, dict[int, dict[int, str]]]]] = {}

    for path, value in output_data.items(): # {"PID-5.1": "Smith", "PID-3": "12345", "PID-3.4.1": "X"}
        if value is None:
            continue
        str_value = str(value)

        # Parse path — strip resource prefix if present (HL7 paths have no "-")
        # resource prefix, but be defensive in case one is passed)
        if path.count("-") >= 1:
            # if the PID part in PID-5.1 is not uppercase then it means there is a resource prefix e.g. Patient-PID-5.1,
            # so we need to remove the resource prefix and keep PID-5.1 as the path, but if the PID part is uppercase
            # then it means there is no resource prefix and we can keep the path as it is.
            path_core = path.split("-", 1)[1] if not path.split("-")[0].isupper() \
                        else path           # keep "PID-5.1" as-is
        else:
            path_core = path

        # Split on "-" then "."
        parts = re.split(r"-|\.", path_core)
        # parts[0] = segment, parts[1] = field, parts[2]? = component, parts[3]? = subcomponent
        if len(parts) < 2: # must have at least segment and field
            continue

        # segment token can be: PID or PID[2]
        seg_token = parts[0].upper()
        seg_match = re.fullmatch(r"([A-Z0-9]{2,})(?:\[(\d+)\])?", seg_token)
        if not seg_match:
            continue
        seg = seg_match.group(1)
        occurrence = int(seg_match.group(2)) if seg_match.group(2) else 1

        try:
            field = int(parts[1])
        except ValueError:
            continue
        comp  = int(parts[2]) if len(parts) > 2 else 1
        sub   = int(parts[3]) if len(parts) > 3 else 1

        # this converts PID-3 into {'PID': {1: {3: {1: {1: '12345'}}}}}
        seg_data.setdefault(seg, {})
        seg_data[seg].setdefault(occurrence, {})
        seg_data[seg][occurrence].setdefault(field, {})
        seg_data[seg][occurrence][field].setdefault(comp, {})
        seg_data[seg][occurrence][field][comp][sub] = str_value

    # ── Serialise each segment ────────────────────────────────────────────────
    # HL7 segment order: MSH first, then alphabetical (reasonable default)
    SEGMENT_ORDER = [
        "EVN", "PID", "PD1", "NK1", "PV1", "PV2",
        "IN1", "IN2", "IN3", "GT1",
        "AL1", "DG1", "PR1",
        "ORC", "OBR", "OBX", "NTE",
        "RXO", "RXE", "RXR", "RXC",
        "FT1", "ZPD",
    ]
    SEGMENT_HAVE_SET = [
        "PID", "NK1", "PV1", "IN1", "IN3", "GT1", "AL1",
        "DG1", "PR1", "OBR", "OBX", "NTE", "FT1"
    ]

    def seg_sort_key(seg_name: str) -> int: # return a segment rank/index.
        try:
            return SEGMENT_ORDER.index(seg_name)
        except ValueError:
            return len(SEGMENT_ORDER)  # unknown segments go last

    lines = [msh]
    segment_counter : dict[str, int] = {} # to track occurrences of each segment type

    # here the seg_data will have all the data of the entire hl7 message
    # the sorted, takes the a list, we have to sort, and the a function that tells how to sort. 
    for seg_name in sorted(seg_data.keys(), key=seg_sort_key): # the lower rank comes first.
        occurrence_map = seg_data[seg_name] # occurance map = {PID: {1: {3: {1: {1: '12345'}}}}, {2: {3: {1: {1: '12345'}}}}}

        # {"PID": 1, "OBX": 2} means the generated message have 1 pid semgnet and 2 obx segments.
        segment_counter[seg_name] = 1 if segment_counter.get(seg_name) is None else segment_counter[seg_name] + 1

        for occ in sorted(occurrence_map.keys()):
            fields_map = occurrence_map[occ] # contain all the fields of one segment
            max_field = max(fields_map.keys()) # max field index for this segment, e.g. 5 for PID
            field_strs: list[str] = []

            for f_idx in range(1, max_field + 1): # include the last field index
                if f_idx not in fields_map:
                    field_strs.append("")
                    continue

                comp_map = fields_map[f_idx]
                max_comp = max(comp_map.keys())
                comp_strs: list[str] = []

                for c_idx in range(1, max_comp + 1):
                    if c_idx not in comp_map:
                        comp_strs.append("")
                        continue

                    sub_map = comp_map[c_idx]
                    max_sub = max(sub_map.keys())

                    if max_sub == 1:
                        comp_strs.append(sub_map[1])
                    else:
                        sub_strs = [sub_map.get(s, "") for s in range(1, max_sub + 1)]
                        comp_strs.append("&".join(sub_strs))

                field_strs.append("^".join(comp_strs) if max_comp > 1 else comp_strs[0])

            if min(fields_map.keys()) > 1 and seg_name in SEGMENT_HAVE_SET:
                # this will allow those fields whose first field is was not present, and they have were allow to have a set id. 
                lines.append(f"{seg_name}|" + str(occ) + "|".join(field_strs))
            else:
                lines.append(f"{seg_name}|" + "|".join(field_strs))

    return "\r\n".join(lines)

if __name__ == "__main__":

    final_output = build_hl7_message(
        output_data={
            "PID[1]-3": "12345",
            "PID[1]-5.1": "Smith",
            "PID[1]-5.2": "John",
            "PID[1]-5.3": "A",
            "PID[1]-3.4.1": "X",

            "PID[2]-3": "12345",
            "PID[2]-5.1": "Smith",
            "PID[2]-5.2": "John",
            "PID[2]-5.3": "A",
            "PID[2]-3.4.1": "X",

            "PV1[1]-1": "1",
            # "PV1[1]-2": "I",
            "PV1[1]-3": "2000^2012^01",

            "PV1[2]-1": "2",
            "PV1[2]-2": "O",
            "PV1[2]-3": "2000^2012^01",
        },
        src="TestApp",
        dest="DestApp",
        msg_type="ADT^A01"
    )

    print(final_output)