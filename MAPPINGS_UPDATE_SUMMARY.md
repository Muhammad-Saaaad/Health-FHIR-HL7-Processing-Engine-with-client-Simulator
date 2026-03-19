# Mappings Update Summary

## Overview
Added comprehensive FHIR R4B and HL7 field mappings for your validated resources (Encounter and Coverage).

## FHIR R4B Encounter Mappings Added

### Encounter-specific Fields
```
Encounter-type[0].text                      → encounter_title
Encounter-reasonCode[0].text                → encounter_complaint
Encounter-diagnosis[0].condition.display    → encounter_diagnosis_display
Encounter-extension[0].url                  → encounter_notes_url
Encounter-extension[0].valueString          → encounter_notes
```

**Purpose**: Maps the 4 core encounter data elements you defined:
1. **Encounter Title** (what the encounter is about) → `encounter_title`
2. **Patient Complaint** (reason for visit) → `encounter_complaint`
3. **Diagnosis** (clinical diagnosis) → `encounter_diagnosis_display`
4. **Consultation Notes** (assessment/follow-up) → `encounter_notes`

## FHIR R4B Coverage Mappings Added/Updated

### Coverage-specific Fields
```
Coverage-type.text                          → coverage_type_text
```

**Purpose**: Added text mapping for Coverage type to capture plain text coverage category (e.g., "Silver") without requiring coding structure.

## HL7 Segment Mappings Added

### NTE (Notes) Segment
```
NTE-1                                       → note_set_id
NTE-2                                       → note_source_type
NTE-3                                       → note_text
NTE-4                                       → note_classification
```

**Purpose**: Maps HL7 Notes segment to capture consultation notes when converting from legacy HL7 systems.

## Cross-System Data Flow

### EHR → Engine → PHR Mapping Chain

When your engine receives data:

**FHIR Input Path** → **Canonical Name** → **HL7 Equivalent**
```
Encounter-identifier[0].value       → encounter_number       ← PV1-19 (visit_number) / PV1-50 (alternate_visit_id)
Encounter-type[0].text              → encounter_title        ← PV1-2 (patient_class) + NTE-3 (note_text)
Encounter-reasonCode[0].text        → encounter_complaint    ← PV1-14 (admit_source) + DG1-4 (diagnosis_description)
Encounter-diagnosis[0].condition    → encounter_diagnosis    ← DG1-3 (diagnosis_code) / DG1-3.2 (diagnosis_name)
Encounter-extension[0].valueString  → encounter_notes        ← NTE-3 (note_text)

Coverage-identifier[0].value        → member_id             ← IN1-53 (patient_member_number)
Coverage-type.text                  → coverage_type_text    ← IN1-35 (coverage_type)
Coverage-beneficiary.reference      → coverage_patient      ← PID-3 (patient_mpi)
Coverage-payor[0].reference         → insurance_company     ← IN1-4 (insurance_company_name)
```

## Implementation Notes

### Bundle Handling
Bundles themselves are NOT tracked in mappings.py (as intended). Only the sub-resources are mapped:
- Bundle.entry[0].resource (Patient) → Patient mappings
- Bundle.entry[1].resource (Coverage) → Coverage mappings

### Identifier Strategy (No `system` field)
Your engine pre-knows source/destination servers via channel configuration, so `system` is unnecessary:
- FHIR: `"identifier": [{"value": "ENC-2024-12345"}]`
- HL7: `PV1-19` (visit_number) or `PV1-50` (alternate_visit_id)

### Text-based Fields for Simplicity
Where your FHIR resources use `.text` instead of `.coding[0]`:
- Encounter-type.text → encounter_title (not requiring SNOMED codes)
- Coverage-type.text → coverage_type_text (supports "Silver", "Gold", etc.)
- Encounter-reasonCode.text → encounter_complaint (plain language complaint)

## File Statistics

| Dictionary | Count | Change |
|------------|-------|--------|
| FHIR_EXACT_CANONICAL | 499 | +6 entries |
| HL7_EXACT_CANONICAL | 423 | +4 entries |
| FHIR_PATTERN_CANONICAL | (unchanged) | — |

## Testing

Validation script confirms all mappings load correctly:
```
✓ Mappings loaded successfully
✓ FHIR entries: 499
✓ HL7 entries: 423
```

## Next Steps

When the InterfaceEngine processes messages:

1. **Extract phase**: Engine parses FHIR/HL7 messages using these path→name mappings
2. **Transform phase**: Canonical names enable cross-system translation
3. **Route phase**: Messages flow to destination systems with consistent field naming
4. **Validation phase**: ensure all required fields map correctly for target system

The mapping is bidirectional:
- **FHIR → HL7**: Uses FHIR_EXACT_CANONICAL to canonical, then reverse-lookup in HL7_EXACT_CANONICAL
- **HL7 → FHIR**: Uses HL7_EXACT_CANONICAL to canonical, then reverse-lookup in FHIR_EXACT_CANONICAL
