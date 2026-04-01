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
