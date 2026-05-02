## Four Steps for adding a new custom Channel.

1. Make and test fhir & Hl7 message if they are valid and follow the protocols.
2. Make sure that they have the same name in the mappings.py file, for individual fields.
3. Make sure that the suggestions are generated correctly from the suggestion.py file and the server profile column also supports it. 
4. Make sure the message should have any duplicate values for the same segments, like PID that was located in the OBR segment 2. 