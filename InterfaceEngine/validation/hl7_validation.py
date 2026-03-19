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
    control_id = f"MSG{uuid4().hex[:8].upper()}"

    msh = (
        f"MSH|^~\\&|{src}||{dest}||{dt}||{msg_type}"
        f"|{control_id}|P|2.5"
    )

    # ── Build segment buffers ─────────────────────────────────────────────────
    # Structure: { segment_type: { field_idx: { comp_idx: { sub_idx: value } } } }
    seg_data: dict[str, dict[int, dict[int, dict[int, str]]]] = {}

    for path, value in output_data.items():
        if value is None:
            continue
        str_value = str(value)

        # Parse path — strip resource prefix if present (HL7 paths have no "-"
        # resource prefix, but be defensive in case one is passed)
        if path.count("-") >= 1:
            path_core = path.split("-", 1)[1] if not path.split("-")[0].isupper() \
                        else path           # keep "PID-5.1" as-is
        else:
            path_core = path

        # Split on "-" then "."
        parts = re.split(r"-|\.", path_core)
        # parts[0] = segment, parts[1] = field, parts[2]? = component, parts[3]? = subcomponent
        if len(parts) < 2:
            continue

        seg   = parts[0].upper()
        try:
            field = int(parts[1])
        except ValueError:
            continue
        comp  = int(parts[2]) if len(parts) > 2 else 1
        sub   = int(parts[3]) if len(parts) > 3 else 1

        seg_data.setdefault(seg, {})
        seg_data[seg].setdefault(field, {})
        seg_data[seg][field].setdefault(comp, {})
        seg_data[seg][field][comp][sub] = str_value

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

    def seg_sort_key(seg_name: str) -> int:
        try:
            return SEGMENT_ORDER.index(seg_name)
        except ValueError:
            return len(SEGMENT_ORDER)  # unknown segments go last

    lines = [msh]

    for seg_name in sorted(seg_data.keys(), key=seg_sort_key):
        fields_map = seg_data[seg_name]
        max_field = max(fields_map.keys())
        field_strs: list[str] = []

        for f_idx in range(1, max_field + 1):
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

        lines.append(f"{seg_name}|" + "|".join(field_strs))

    return "\r\n".join(lines)



# async def build_hl7_message(output_data, src, dest, msg_type):
#     segments = {}
#     date = datetime.now()
#     dt = datetime.strptime(str(date), "%Y-%m-%d %H:%M:%S.%f")
#     date = dt.strftime("%Y%m%d%H%M%S")

#     header = f"MSH|^~\&|{src}||{dest}||{date}||{msg_type}|MSG{str(uuid.uuid4())}|P|2.5"
#     for path, value in output_data.items():
#         # example: PID-5.1
#         segment = path.split("-")[0]
#         field = int(path.split("-")[1].split(".")[0])
#         comp = int(path.split(".")[1]) if "." in path else None

#         segments.setdefault(segment, [])

#         while len(segments[segment]) < field:
#             segments[segment].append("")

#         if comp:
#             comps = segments[segment][field-1].split("^")
#             while len(comps) < comp:
#                 comps.append("")
#             comps[comp-1] = str(value)
#             segments[segment][field-1] = "^".join(comps)
#         else:
#             segments[segment][field-1] = str(value)

#     msg = ""
#     for seg, fields in segments.items():
#         msg += seg + "|" + "|".join(fields) + "\n"
#     msg = header+"\n"+msg
#     return msg

if __name__ == "__main__":
    pass