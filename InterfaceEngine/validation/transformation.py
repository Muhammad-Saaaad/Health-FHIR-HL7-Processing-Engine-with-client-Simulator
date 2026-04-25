import re

def regex_replace_with_template(value: str, pattern_from: str, pattern_to: str) -> str:
    r"""
    Replace using regex with capture groups - bidirectional!
    
    Forward example:
        value: "2"
        pattern_from: r"\\d+"
        pattern_to: r"patient/\\d+"
    Captures the \d+ convert it into (\\d+), then replaces it with patient/\1 = "patient/2"
    
    Reverse example:
        value: "patient/2"
        pattern_from: r"patient/\\d+"
        pattern_to: r"\\d+"
    Captures the \d+ convert it into (\d+), then replaces entire match with just \1 = "2"
    """
    # Find common regex patterns
    common_patterns = [r"\d+", r"\d", r"\w+", r"\w", r".*", r".+", r"[^/]+", r"[^\s]+"]
    captured_pattern = None
    
    for regex_pattern in common_patterns:
        if regex_pattern in pattern_from:
            captured_pattern = regex_pattern
            break
    
    if not captured_pattern:
        return re.sub(pattern=pattern_from, repl=pattern_to, string=value)
    
    # Wrap the variable part in a capture group
    pattern_from_captured = pattern_from.replace(captured_pattern, f"({captured_pattern})", 1)
    
    # Replace that pattern in pattern_to with the capture group reference \1
    replacement_template = pattern_to.replace(captured_pattern, r"\1", 1)
    
    print(f"Value: {value}")
    print(f"Pattern from: {pattern_from}")
    print(f"Pattern from (with capture): {pattern_from_captured}")
    print(f"Replacement template: {replacement_template}")
    print()
    
    return re.sub(pattern=pattern_from_captured, repl=replacement_template, string=value)

# --------------------------------------------------------------------------------------------------

def get_segment_name_and_counter(segment: str) -> tuple[str, int, str]:
        segment_name = segment.split("-", 1)[0] # PID[1]-5.1 -> PID[1]
        segment_core_path = segment.split("-", 1)[1] # PID-5.1 -> 5.1
        # PID[1] -> PID, 1 or Patient[1] -> Patient, 1
        # PID -> PID, 0
        segment_name, counter = (segment_name, 0) if "[" not in segment_name else (segment_name.split("[")[0], int(re.search(r"\[(\d+)\]", segment_name).group(1)))
        return segment_name, counter, segment_core_path

def increment_segment(output_data: dict | None=None, segment_path: str="", list_data: list | None = None) -> str:
    """
    this can work with both fhir and hl7 and data can be in list or dictionary.
    """
    if output_data is None and list_data is None:
        raise ValueError("Either output_data or list_data must be provided.")

    input_segment_name, input_segment_counter, input_segment_core_path = get_segment_name_and_counter(segment_path)

    for key in output_data.keys() if list_data is None else list_data: # the key also contain the path.
        output_segment_name, output_segment_counter, output_segment_core_path = get_segment_name_and_counter(key)

        if (output_segment_name == input_segment_name) and (output_segment_core_path == input_segment_core_path):
           input_segment_counter = max(output_segment_counter , input_segment_counter)
    
    final_path = input_segment_name + f"[{input_segment_counter + 1}]" + "-" + input_segment_core_path
    return final_path

# def increment_segment(segment : str) -> str:
#     """
#     Increment the last number in a string by 1. If there is no number, add [1] at the end.
#     Examples:
#         "PID-5.1" → "PID[1]-5.1"
#         "Patient-name" → "Patient[1]-name"
#         "Patient[1]-name" → "Patient[2]-name"
#         "Patient[2]-name" → "Patient[3]-name"
#     """
#     segment_parts = segment.split("-", 1) # PID-5.1 -> ["PID", "5.1"] -> PID[1]-5.1

#     match = re.search(r"\[(\d+)\]", segment_parts[0]) # find [digit] in Patient[1] or PID[1] or in PID
#     if match: # if there is a match, increment the number
#         number = int(match.group(1))
#         incremented_number = number + 1
#         output= re.sub(r"\[\d+\]", f"[{incremented_number}]", segment_parts[0]) + "-" + segment_parts[1]
#         return output
#     else:
#         # if theree was no digit in the segment or resource name then by default add 1.
#         if len(segment_parts) == 2:
#             output= f"{segment_parts[0]}[1]-{segment_parts[1]}"
#             return output
#         else:
#             return

def fill_duplicate_missing_values(output_data):
    """
    This will take the outpput_data, that I will be send to the destination server. it will check
    if any value in the segments_to_fill is not available, or not found. if yes then it will fill it
    with the first occurace of that segment, if first occurace is also not available then it won't do anything else.

    """
    segments_to_fill = ["OBR-2"]
    for segment in segments_to_fill:
        segment_max_count = 0

        # Extract segment family name before '-'.
        # "OBR-2" -> "OBR"
        segment_simple_name = segment.split("-")[0]

        # Stores which normalized segment matched first (e.g., "OBR-2").
        matched_segment = ""

        # First available value for the target field; this becomes the default fill value.
        first_occurance_segment_value = None

        # Scan all existing output keys to:
        #   1) discover max occurrence index
        #   2) find first value for the exact segment-field target
        for output_key in output_data.keys():
            # Strip occurrence syntax to get family name.
            # Examples:
            #   "Patient[1]-name" -> "Patient"
            #   "OBR[1]-2" -> "OBR"
            #   "OBR-2" -> "OBR"
            output_simple_name = output_key.split("[", 1)[0].split("]", 1)[0]

            # If this key belongs to the same segment family (e.g., OBR), try reading occurrence index.
            if output_simple_name == segment_simple_name:
                try:

                    output_count = int(output_key.split("[",1)[1].split("]",1)[0]) # Patient[1]-name -> 1, OBR[1]-2 -> 1, OBR-2 -> error but I will handle it with try except and consider it as 0
                except:
                    # Non-indexed format like "OBR-2" is treated as 0.
                    output_count = 0

                # Keep the highest observed occurrence index.
                if output_count > segment_max_count:
                    segment_max_count = output_count
                

            output_simple_name += "-" + output_key.split("-")[-1] # Patient[1]-name -> Patient-name or OBR-2 -> OBR-2 or OBR[1]-2 -> OBR-2
            
            if output_simple_name not in segments_to_fill or first_occurance_segment_value is not None:
                continue
            matched_segment = output_simple_name
            first_occurance_segment_value = output_data[output_key]


        if matched_segment != "" and segment_max_count >1:
            print("first occurance segment value for ", matched_segment, " is ", first_occurance_segment_value)
            for i in range(1, segment_max_count+1):
                segment_to_fill = segment_simple_name + f"[{i}]" + "-" + segment.split("-")[1] # OBR[1]-2, OBR[2]-2, OBR[3]-2
                if segment_to_fill not in output_data:
                    output_data[segment_to_fill] = first_occurance_segment_value
                    print("filling the missing value for ", segment_to_fill, " with value ", first_occurance_segment_value)
    
    return output_data


if __name__ == "__main__":

    fill_duplicate_missing_values({'PID[1]-3': '1228', 'OBR[1]-2': '62', 'OBR[1]-4.1': '42300-4', 'OBR[2]-4.1': '38045-1', 'OBR[3]-4.1': '36053-7', 'OBR[1]-4.2': 'MR Thyroid gland', 'OBR[2]-4.2': 'US Parathyroid gland', 'OBR[3]-4.2': 'MR Parathyroid gland'})
    # output_data = {
    #     "Patient[1]-name": "John Doe",
    #     "Patient[2]-name": "Jane Doe",

    #     "Patient-identifier[1].value": "12345",
    #     "Patient-identifier[2].value": "67890",

    #     "PID[1]-5.1": "John",
    #     "PID[2]-5.1": "Jane",
    #     "ServiceRequest[2]-name": "Blood Test"
    # }

    # print("Patient-identifier[1].value -> ",increment_segment(output_data, "Patient-identifier[1].value"))
    # print("\nPatient[1]-identifier[0].type.coding[0].code -> ",increment_segment(output_data, "Patient[1]-identifier[0].type.coding[0].code"))
    # print("\nPatient-name -> ",increment_segment(output_data, "Patient-name"))
    # print("\nPatient[1]-name.text -> ",increment_segment(output_data, "Patient[1]-name.text"))
    # print("\nPatient[2]-name -> ",increment_segment(output_data, "Patient[2]-name"))
    # print("\nPID-5.1 -> ",increment_segment(output_data, "PID-5.1"))
    # print("\nPID[2]-5.2 -> ",increment_segment(output_data, "PID[2]-5.2"))
    # print("\nServiceRequest[2]-name -> ",increment_segment(output_data, "ServiceRequest-name"))
    # print("\nTest-name -> ",increment_segment(output_data, "Test-name"))

    # string = "Patient[23]"
    # pattern = r"\[(\d+)\]"
    # print(re.search(pattern, string).group(1))
    # print(regex_replace_with_template("Practitioner/a123-c", "Practitioner/.+", ".+"))
    # print(regex_replace_with_template("a123-c/VID", ".+", "Practitioner/.+"))