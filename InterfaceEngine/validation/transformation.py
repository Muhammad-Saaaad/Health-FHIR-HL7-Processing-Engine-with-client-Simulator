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

def increment_segment(segment : str) -> str:
    """
    Increment the last number in a string by 1. If there is no number, add [1] at the end.
    Examples:
        "PID-5.1" → "PID[1]-5.1"
        "Patient-name" → "Patient[1]-name"
        "Patient[1]-name" → "Patient[2]-name"
        "Patient[2]-name" → "Patient[3]-name"
    """
    segment_parts = segment.split("-", 1) # PID-5.1 -> ["PID", "5.1"] -> PID[1]-5.1

    match = re.search(r"\[(\d+)\]", segment_parts[0]) # find [digit] in Patient[1] or PID[1] or in PID
    if match: # if there is a match, increment the number
        number = int(match.group(1))
        incremented_number = number + 1
        output= re.sub(r"\[\d+\]", f"[{incremented_number}]", segment_parts[0]) + "-" + segment_parts[1]
        print("Input path: ", segment, " --> Output path: ", output)
        return output
    else:
        # if theree was no digit in the segment or resource name then by default add 1.
        if len(segment_parts) == 2:
            output= f"{segment_parts[0]}[1]-{segment_parts[1]}"
            print("Input path: ", segment, " --> Output path: ", output)
            return output
        else:
            return


if __name__ == "__main__":

    increment_segment("Patient-identifier[1].value")
    increment_segment("Patient-identifier[0].type.coding[0].code")
    increment_segment("Patient-name.text")
    increment_segment("Patient[1]-name.text")
    increment_segment("Patient[2]-name")
    increment_segment("PID-5.1")
    increment_segment("PID[2]-5.2")
    increment_segment("ServiceRequest[2]-name")