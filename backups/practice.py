# l1, l2 = [], []
# l1.append(1)
# l2.append(2)

# print(type(l1))
# print(type(l2))

import re

# value = "21 223"

# result = re.sub(r"\d+", r"patient", value, count=1)

# print(result)

def regex_replace_with_template(value: str, pattern_from: str, pattern_to: str) -> str:
    r"""
    Replace using regex with capture groups - bidirectional!
    
    Forward example:
        value: "2"
        pattern_from: r"\\d+"
        pattern_to: r"patient/\\d+"
    Captures the \d+ as (\\d+), then replaces it with patient/\1 = "patient/2"
    
    Reverse example:
        value: "patient/2"
        pattern_from: r"patient/\\d+"
        pattern_to: r"\\d+"
    Captures the \d+ as (\d+), then replaces entire match with just \1 = "2"
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
    
    print(f"Pattern captured: {captured_pattern}")
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


# Test forward: "2" → "patient/2"
# print("=== FORWARD ===")
# id_ = "2"
# regex_dictionary = {"from": r"\d+", "to": r"patient/\d+"}
# result = regex_replace_with_template(id_, regex_dictionary["from"], regex_dictionary["to"])
# print(f"Result: {result}\n")

# # Test reverse: "patient/2" → "2"
# print("=== REVERSE ===")
# id_ = "patient/2"
# regex_dictionary = {"from": r"patient/\d+", "to": r"\d+"}
# result = regex_replace_with_template(id_, regex_dictionary["from"], regex_dictionary["to"])
# print(f"Result: {result}")

# value = "2"
# # print(re.sub(pattern=r"patient/(\d+)", repl=r"\1", string=value))
# # print(re.findall(r"patient/(\d+)", value))

# # print(re.sub(pattern=r"patient/(\d+)", repl=r"\1", string=value))
# print(re.sub(pattern=r"\d+", repl=r"patient/()", string=value))
# lines = ["hi there-", "how are you"]
# line = "\r\n".join(lines)
# print(line.splitlines()[1:])

# rules = [1,2,3,4,5]
# incomming_rules = [2,3,3,4,5]
# for rule in rules:
#     # for incoming_rule in incomming_rules:
#     if rule in incomming_rules:
#         occurance_of_rule = incomming_rules.count(rule)
#         for i in range(occurance_of_rule):
#             print(rule)
    # process_rule(rule)

# from collections import Counter

# l = ["ali","usama","ahemd","ahemd","abc","dev"]
# print(Counter(l))

from datetime import datetime

# date = datetime.now().date()
# date_formate_to_chnage = datetime.strptime(str(date), "%Y-%m-%d")
# formated_date = date_formate_to_chnage.strftime("%B %d, %Y")
# print(formated_date)

# t1 = (4, 20)
# t2 = (4, 30)
# print(t1 < t2)

# dt_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
# print(dt_str)  # 2026-05-02T10:30:00Z

# # Convert to second format
# dt_converted = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y%m%d%H%M%S")
# print(dt_converted)  # 20260502103000

import json

data = {
    "id": "123",
    "name": "John Doe"
}

json_str = json.dumps(data)
print(json_str)  # {"id": "123", "name": "John Doe"}