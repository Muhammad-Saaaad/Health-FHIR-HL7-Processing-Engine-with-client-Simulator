# Welcome! A Beginner's Guide to This Project

This guide assumes you know **nothing about backend development**. Read it top to bottom — every concept is explained the first time it appears.

---

## 1. The Story (read this first)

Imagine four organizations in the real world:

| Folder in this repo | Real-world thing | What it does |
| --- | --- | --- |
| `EHR/` | A **hospital** (Electronic Health Record) | Registers patients, doctor visits, sends lab orders and insurance claims |
| `LIS/` | A **laboratory** (Lab Information System) | Receives lab orders, runs tests, sends results back |
| `Payer/` | An **insurance company** | Receives claims, approves/rejects them |
| `phr/` | A **patient's mobile app** (Personal Health Record) | Lets a patient see their own visits and reports |

These four need to exchange data constantly: the hospital sends lab orders to labs, claims to insurers, visit summaries to the patient app, and they all send replies back.

**Problem:** they don't speak the same language.
- Some speak **FHIR** — a modern format based on JSON (structured text that looks like `{"name": "Ali", "age": 30}`).
- Some speak **HL7 v2** — an older hospital format that looks like text lines separated by `|` pipes:
  `MSH|^~\&|EHR-1||LIS-1||20260203120000||ADT^A01|MSG00001|P|2.5`

**Solution:** the `InterfaceEngine/` folder. Think of it as a **post office + translator** sitting in the middle:

```
 Hospital (EHR) ──┐                       ┌── Lab 1 (LIS)
                  │                       ├── Lab 2 (LIS)
                  ├──► InterfaceEngine ───┤
 Insurance ───────┘    (translates +      ├── Insurance (Payer)
                        routes messages)  └── Patient app (PHR)
```

Every message goes **through the engine**. The engine looks at where it came from, transforms the data into the format the receiver understands, and delivers it. Nobody talks to anybody directly.

---

## 2. Backend Concepts You Need (10-minute crash course)

**Server** — a program that runs forever, waiting for requests. Each folder here (EHR, LIS, Payer, phr, InterfaceEngine) is one server.

**Port** — a number that identifies a program on a machine, like an apartment number in a building. Our servers:

| Server | Port | Address when running |
| --- | --- | --- |
| EHR (hospital) | 8001 | http://localhost:8001 |
| LIS (lab) | 8002 | http://localhost:8002 |
| Payer (insurance) | 8003 | http://localhost:8003 |
| PHR (patient app) | 8004 | http://localhost:8004 |
| **InterfaceEngine** | **9000** | http://localhost:9000 |

**API / Endpoint** — a URL that a server listens on. Example: when the hospital frontend wants to add a patient, it sends data to `http://localhost:8001/patients`. The path `/patients` is an "endpoint".

**HTTP methods** — the verb of a request. `GET` = "give me data", `POST` = "here is new data, save/process it", `PUT` = "update", `DELETE` = "remove".

**JSON** — the standard way to send structured data: `{"nic": "37201-1234567-8", "name": "Ali"}`.

**Database (DB)** — where data is permanently stored in tables (like Excel sheets with rules). This project uses **SQL Server**. Each system has its **own** database.

**FastAPI** — the Python library we use to build the servers. You define a function, decorate it with a URL, and FastAPI runs it when a request hits that URL:

```python
@router.post("/patients")              # ← "when someone POSTs to /patients..."
def add_patient(patient, db):          # ← "...run this function"
    db.add(new_patient)                # save to database
    return {"message": "added"}        # reply to the caller
```

**uvicorn** — the program that actually runs a FastAPI app (`python main.py` starts it).

**SQLAlchemy / models** — Python classes that mirror database tables. Look at any `model.py` / `models.py`: each class = one table, each attribute = one column.

**Alembic / migrations** — version control for the database structure. When someone adds a column to a model, they also add a "migration" file; running `alembic upgrade head` applies it to your database. (See `MIGRATIONS` notes in the repo / ask the team.)

**async / await** — Python's way of doing many slow things (like waiting for another server to reply) at the same time without freezing. You'll see `async def` and `await` everywhere — read them as "this function can pause while waiting, letting other work continue."

---

## 3. The Journey of One Message (the most important section)

Let's follow what happens when a hospital receptionist registers a new patient. Read this slowly — once you understand this flow, you understand the whole project.

### Step 1 — Hospital saves the patient
File: [EHR/api/patient.py](EHR/api/patient.py), function `add_patient`.
- The frontend POSTs the patient's details to the EHR server.
- The EHR saves the patient into **its own** database.
- It then builds a **FHIR Bundle** — a JSON package containing a `Patient` resource and a `Coverage` (insurance) resource.

### Step 2 — Hospital sends the bundle to the engine
File: [EHR/api/engine_service.py](EHR/api/engine_service.py), function `send_to_engine`.
- The bundle is POSTed to `http://127.0.0.1:9000/fhir/add-patient` with a header `System-Id: EHR-1` ("this message comes from hospital EHR-1").

### Step 3 — Engine receives and validates
File: [InterfaceEngine/main.py](InterfaceEngine/main.py), function `ingest` → `_process_message`.
- The engine looks up which **server** has `system_id = EHR-1` and whether `/fhir/add-patient` is a registered **endpoint** for it.
- It checks the **routes** (also called channels): "when data arrives at this endpoint, where should it go?" One endpoint can have many routes — e.g. add-patient goes to Lab 1, Lab 2, AND the insurance company.

### Step 4 — Targeted delivery check
- If the bundle contains `identifier.value` like `"Payer-1"`, the engine narrows delivery: within the *payer* category, only `Payer-1` gets it; other categories (labs) still get it normally.
- If there's no identifier, the message goes to **all** routes.

### Step 5 — Transformation (the "translator" part)
File: [InterfaceEngine/main.py](InterfaceEngine/main.py), function `route_worker`.
- Each route has **mapping rules** stored in the engine's database: "take the value at FHIR path `Patient-name[0].text` and put it at HL7 path `PID-5`".
- Rules can `copy`, `map` (translate values like male→M), `format` (change date formats), `concat` (join fields), or `split` (break one field into many).
- The worker applies all the rules and builds a brand-new message in the destination's format (HL7 text for labs, FHIR JSON for the patient app, etc.).

### Step 6 — Delivery
- The worker POSTs the transformed message to the destination server, e.g. `http://localhost:8002/get/new-patient` for the lab, with headers saying who originally sent it (`Src-System-Id: EHR-1`).

### Step 7 — Destination saves it
File: [LIS/api/engine_service.py](LIS/api/engine_service.py), function `add_patient`.
- The lab parses the HL7 text, extracts the patient fields, and saves the patient into **its own** database — including `dest_system_id = "EHR-1"` so it remembers which hospital this patient came from.

### Step 8 — The reply comes back the same way (later)
- When the lab finishes a test, [LIS/api/results.py](LIS/api/results.py) builds an HL7 result message with `MSH-5 = EHR-1` ("deliver this to EHR-1") and sends it to the engine, which routes it back to the right hospital. Full circle.

---

## 4. Folder Map — Where to Find Things

Every system follows the same layout, so learning one teaches you all five:

```
EHR/  (same shape for LIS, Payer, phr, InterfaceEngine)
├── main.py            ← entry point: creates the app, wires everything, starts the server
├── model.py           ← database tables as Python classes
├── database.py        ← how to connect to the database
├── api/               ← one file per feature area (patient.py, claim.py, ...)
│   └── engine_service.py  ← everything related to talking WITH the engine
├── schemas/           ← shapes of request/response data (what fields, what types)
├── migrations/        ← database structure history (Alembic)
└── logs/              ← log files the server writes while running
```

The engine has two extra pieces worth knowing:
- `InterfaceEngine/validation/` — the FHIR/HL7 parsing, path-extraction, and message-building logic (the translator's dictionary).
- `InterfaceEngine/api/route.py`, `endpoint.py`, `server.py` — CRUD APIs for configuring servers/endpoints/routes (this is how routes get into the engine's DB in the first place).

---

## 5. Suggested Reading Order (for the new person)

Don't read everything. Read in this order, and run the system while you read:

1. **This file**, especially section 3 (the journey).
2. [EHR/api/patient.py](EHR/api/patient.py) — one well-commented endpoint, start to finish. Learn the FastAPI pattern: decorator → function → DB → response.
3. [EHR/model.py](EHR/model.py) — see how tables are defined. Compare with the real DB in SQL Server Management Studio if you can.
4. [EHR/api/engine_service.py](EHR/api/engine_service.py) — how a system sends to / receives from the engine.
5. [InterfaceEngine/main.py](InterfaceEngine/main.py) — the big one. Read in this order: `check_health` (trivial), `ingest` (entry point), `_process_message` (validation + routing), `route_manager` (spawns workers), `route_worker` (transformation + delivery). Skip the rest at first.
6. [INTERFACE_ENGINE_FLOW_AND_ISSUES.md](INTERFACE_ENGINE_FLOW_AND_ISSUES.md) — the advanced companion doc: detailed flow, known issues, and the changelog of recent fixes. Read it *after* the code makes basic sense.

---

## 6. Running the Project

1. **Prerequisites:** Python, SQL Server running locally, and the project's virtual environment (`health-venv` at the repo root).
2. **Environment:** a `.env` file at the repo root defines the database URLs (`DATABASE_URL_LIS`, etc.). Ask a teammate for a copy — never commit it.
3. **Database setup:** in each of `EHR/`, `LIS/`, `Payer/` run:
   ```powershell
   ..\health-venv\Scripts\alembic.exe upgrade head
   ```
4. **Start each server** (each in its own terminal, from inside its folder):
   ```powershell
   ..\health-venv\Scripts\python.exe main.py
   ```
   Start the **InterfaceEngine first**, then the others (the engine health-checks the rest).
5. **Verify:** open http://localhost:9000/docs — FastAPI gives every server a free interactive API page at `/docs` where you can try endpoints from the browser. This is the single best learning tool in the project: open `/docs` on each server and poke around.

---

## 7. Glossary (quick reference)

| Term | Meaning |
| --- | --- |
| FHIR | Modern healthcare data format (JSON-based). "Bundle" = a package of several resources. |
| HL7 v2 | Older healthcare format; text lines (segments) split by `\|`. `MSH` = header segment, `PID` = patient segment, `OBR` = lab order, `OBX` = result value. |
| MSH-5 | 5th field of the HL7 header = "receiving application" = who this message is for. |
| NIC | National ID card number — used as the patient identifier across all systems. |
| system_id | Unique ID of each connected system (e.g. `EHR-1`, `LIS-2`, `Payer-1`). Category is the part before the dash. |
| Route / Channel | A configured pipe in the engine: source endpoint → destination endpoint + mapping rules. |
| Mapping rule | One field-to-field transformation instruction (copy/map/format/concat/split). |
| Endpoint fields | The list of data paths the engine expects at an endpoint (e.g. `Patient-name[0].text`). |
| route_worker | A background task inside the engine that transforms and delivers messages for one route (3 workers per route). |
| Ingest | The engine's generic entry point: `POST /{any-path}` — all systems send messages there. |
| Batch | `POST /batch` — many messages in one request, processed in order. |
| Park / redelivery | If a destination is down, the engine stores the message in memory and retries automatically when the destination comes back. |
| Migration | A versioned change to database structure, applied with `alembic upgrade head`. |
