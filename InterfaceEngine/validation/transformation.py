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


if __name__ == "__main__":

    output_data = {
        "Patient[1]-name": "John Doe",
        "Patient[2]-name": "Jane Doe",

        "Patient-identifier[1].value": "12345",
        "Patient-identifier[2].value": "67890",

        "PID[1]-5.1": "John",
        "PID[2]-5.1": "Jane",
        "ServiceRequest[2]-name": "Blood Test"
    }

    # print("Patient-identifier[1].value -> ",increment_segment(output_data, "Patient-identifier[1].value"))
    # print("\nPatient[1]-identifier[0].type.coding[0].code -> ",increment_segment(output_data, "Patient[1]-identifier[0].type.coding[0].code"))
    print("\nPatient-name -> ",increment_segment(output_data, "Patient-name"))
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