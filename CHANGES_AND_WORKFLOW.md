# Interface Engine — Bug Fixes & System Workflow

## What Was Broken

When a patient was added via the EHR API, the Interface Engine returned:

```
502 Bad Gateway — One or more downstream deliveries failed:
  Route 8: http://127.0.0.1:8002/get/new-patient → 500 Internal Server Error
  Route 11: http://127.0.0.1:8003/get/registed_patient → 422 / 400
```

Both LIS (port 8002) and Payer (port 8003) were crashing because the HL7 message they received had **no data fields** — only the MSH header. The root cause was in `InterfaceEngine/main.py` inside the `ingest()` function.

---

## Root Causes & Fixes

### Bug 1 — HL7 Path Extraction Treated the Whole Message as One Segment

**File:** `InterfaceEngine/main.py` → `ingest()`

**What happened:**
```python
# OLD (broken)
paths = hl7_extract_paths(payload)   # ❌ whole HL7 string passed as one segment
```

`hl7_extract_paths(segment)` expects a **single segment** like `"PID|1||12345||Smith^John"`. But `payload` was the entire multi-line HL7 message. It split the whole string on `|` as if it were one flat segment, producing garbage paths like `"MSH-1"` instead of `"PID-3"`, `"PID-7"` etc.

Since the paths were wrong, `src_path_to_value` was empty → `output_data` was empty → the HL7 message built for LIS/Payer had only the auto-generated `MSH` header line and no `PID` segment.

**Fix:**
```python
# NEW (correct) — iterate each segment line, skip MSH
paths = []
for segment in payload.split('\n')[1:]:   # [1:] skips the MSH header
    if not segment.strip():
        continue
    _, seg_paths = hl7_extract_paths(segment)   # one segment at a time ✓
    paths.extend(seg_paths)

src_path_to_value = get_hl7_value_by_path(hl7_message=payload, paths=paths)
```

This mirrors exactly how `add_hl7_endpoint_fields()` parses the sample message during endpoint registration.

---

### Bug 2 — FHIR Bundle Paths Prefixed with `"Bundle-"` Instead of Resource Type

**File:** `InterfaceEngine/main.py` → `ingest()`

**What happened:**
```python
# OLD (broken)
resource_type = payload.get("resourceType", "Unknown")  # → "Bundle"
raw_paths = fhir_extract_paths(payload)                  # traverses whole bundle
paths = [f"{resource_type}-{p}" for p in raw_paths]     # → "Bundle-entry[0].resource.birthDate" ❌
```

The EHR sends a **FHIR Bundle** containing a `Patient` and a `Coverage` resource. The old code extracted paths from the whole Bundle object and prefixed them all with `"Bundle-"`. But the database stores paths like `"Patient-birthDate"` and `"Coverage-identifier[0].value"` (registered at endpoint creation time via `add_fhir_endpoint_fields()`).

No paths ever matched → `src_path_to_value` was empty → HL7 output had no fields.

**Fix:**
```python
# NEW (correct) — iterate each entry resource, prefix with that resource's type
resource_type = payload.get("resourceType", "Unknown")
if resource_type == "Bundle":
    paths = []
    for entry in payload.get("entry", []):
        resource = entry.get("resource", {})
        res_type = resource.get("resourceType", "Unknown")   # "Patient" or "Coverage"
        raw_paths = fhir_extract_paths(resource)
        paths.extend([f"{res_type}-{p}" for p in raw_paths])  # "Patient-birthDate" ✓

# Value extraction also passes each entry resource object directly
for entry in payload.get("entry", []):
    resource = entry.get("resource", {})
    res_type = resource.get("resourceType", "Unknown")
    raw_paths = fhir_extract_paths(resource)
    for p in raw_paths:
        full_path = f"{res_type}-{p}"
        value = get_fhir_value_by_path(obj=resource, path=full_path)
        src_path_to_value[full_path] = value
```

---

## Full System Workflow — Patient Registration

```
Client (Postman / Frontend)
        |
        | POST /patients  {nic, name, dob, gender, insurance...}
        v
    EHR (port 8001)
        | 1. Validate NIC uniqueness
        | 2. db.flush() — saves patient to EHR DB (not committed yet)
        | 3. Build FHIR Bundle (Patient resource + Coverage resource)
        |
        | POST /fhir/add-patient  {FHIR Bundle JSON}
        v
  Interface Engine (port 9000)
        | 1. Look up endpoint URL in DB → find server protocol = "FHIR"
        | 2. Read FHIR Bundle from request body
        | 3. Detect resourceType = "Bundle"
        | 4. For each entry resource (Patient, Coverage):
        |       - Extract paths:  Patient-birthDate, Coverage-identifier[0].value ...
        |       - Extract values: src_path_to_value = { "Patient-birthDate": "2003-02-22", ... }
        | 5. For each Route configured for this endpoint:
        |       a. Apply mapping rules (copy / map / format / concat / split)
        |          e.g. Patient-birthDate  →  format  →  PID-7 (YYYYMMDD)
        |               Patient-gender     →  map     →  PID-8 (M/F)
        |       b. Build output_data = { "PID-3": "...", "PID-7": "20030222", ... }
        |       c. Build HL7 v2.x message:
        |          MSH|^~\&|EHR||LIS||20260222||ADT|MSG...|P|2.5
        |          PID|1||<mpi>||<name>||20030222|M|...
        |       d. POST HL7 plain-text to destination
        |
        |──── POST /get/new-patient (text/plain HL7) ────► LIS (port 8002)
        |                                                     | Parse PID segment
        |                                                     | Save patient to LIS DB
        |                                                     ◄── 200 OK ────────────
        |
        |──── POST /get/registed_patient (text/plain HL7) ── Payer (port 8003)
        |                                                     | Parse PID + IN1 segments
        |                                                     | Upsert patient in Payer DB
        |                                                     ◄── 200 OK ────────────
        |
        | All deliveries succeeded → return 200 OK
        v
    EHR (port 8001)
        | db.commit() — patient record permanently saved
        v
Client ◄── 201 Created  {"message": "data inserted sucessfully"}
```

---

## Rollback Mechanism

If **any** downstream delivery fails (LIS or Payer returns non-200):

| Step | What happens |
|------|-------------|
| 1 | `route_worker` catches the error → `result_future.set_exception(...)` |
| 2 | `ingest()` awaits all futures → collects errors |
| 3 | Raises **502 Bad Gateway** with details of which route/destination failed |
| 4 | EHR's `engine_service.register_engine()` sees non-200 → raises `Exception` |
| 5 | `add_patient()` catches exception → `db.rollback()` |
| 6 | EHR patient record is **removed** — data stays consistent across all systems |

---

## Key Files Changed

| File | What Changed |
|------|-------------|
| `InterfaceEngine/main.py` | `ingest()` — HL7 segment parsing (Bug 1) + FHIR Bundle path extraction (Bug 2) |
