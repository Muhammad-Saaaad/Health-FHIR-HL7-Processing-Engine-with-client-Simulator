# Health FHIR/HL7 Processing Engine with Client Simulator

A healthcare data interoperability platform that enables hospitals, laboratories, insurance companies, and patient portals to exchange clinical data through a central Interface Engine. The engine translates between **FHIR R4** (modern JSON) and **HL7 v2.x** (legacy pipe-delimited) formats in real time, routing messages to the correct destinations with configurable transformation rules.

---

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Architecture Overview](#architecture-overview)
- [How It Works](#how-it-works)
- [Systems](#systems)
- [Message Flow Example](#message-flow-example)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Multi-Tenant Design](#multi-tenant-design)
- [Resilience & Error Handling](#resilience--error-handling)
- [Load Testing](#load-testing)
- [Project Structure](#project-structure)

---

## Why This Exists

Healthcare systems rarely speak the same language. A hospital's Electronic Health Record (EHR) might send data as FHIR JSON, while the lab it partners with only understands HL7 v2 pipe-delimited messages. Insurance companies, patient portals, and other systems each have their own formats and endpoints.

This project solves that problem by acting as a **central message broker and translator**:

- **Format Translation** — Converts between FHIR R4 and HL7 v2.x automatically based on configured mapping rules.
- **Smart Routing** — Delivers messages to the right destinations, with support for targeted delivery (e.g., send only to a specific insurer) and fan-out broadcasting.
- **Multi-Tenancy** — Multiple hospitals, labs, and insurers can coexist, each with isolated data but shared infrastructure.
- **Resilience** — If a destination system is down, messages are parked and automatically retried when it comes back online.

---

## Architecture Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   EHR        │     │   LIS        │     │   Payer      │     │   PHR        │
│  (Hospital)  │     │  (Lab)       │     │ (Insurance)  │     │ (Patient App)│
│  Port 8001   │     │  Port 8002   │     │  Port 8003   │     │  Port 8004   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │                    │
       │    FHIR JSON       │    HL7 v2          │    HL7 v2          │    FHIR JSON
       │                    │                    │                    │
       └────────────┬───────┴────────────┬───────┴────────────┬──────┘
                    │                    │                    │
                    ▼                    ▼                    ▼
            ┌─────────────────────────────────────────────────────┐
            │              Interface Engine (Port 9000)           │
            │                                                     │
            │  ┌─────────┐  ┌──────────┐  ┌───────────────────┐  │
            │  │ Validate │→ │  Route   │→ │ Transform & Send  │  │
            │  │ Message  │  │  Lookup  │  │ (FHIR↔HL7)       │  │
            │  └─────────┘  └──────────┘  └───────────────────┘  │
            │                                                     │
            │  ┌──────────────┐  ┌────────────────────────────┐  │
            │  │ Park & Retry │  │ Audit Log (DB + File)      │  │
            │  └──────────────┘  └────────────────────────────┘  │
            └─────────────────────────────────────────────────────┘
```

---

## How It Works

### 1. Message Ingestion

When a system (e.g., an EHR registering a new patient) sends data, it POSTs to the Interface Engine with a `System-Id` header identifying itself and a path identifying the operation (e.g., `/fhir/add-patient`).

### 2. Validation & Path Extraction

The engine validates the source system, looks up the endpoint, and extracts all data fields:

- **FHIR messages** → Recursively extracts paths like `Patient-name[0].text`, `Coverage-identifier[0].value`
- **HL7 messages** → Parses segments into paths like `PID-3` (patient ID), `PID-5.1` (last name)

### 3. Route Matching

The engine looks up all configured routes for the source endpoint. Routes define:
- **Source** → which system and endpoint the message came from
- **Destination** → which system and endpoint to deliver to
- **Mapping Rules** → how to transform each field (copy, map, format, concat, split)

### 4. Targeted Delivery

Messages can optionally target a specific destination:
- FHIR: `Bundle.identifier.value = "Payer-1"` narrows delivery within that category
- HL7: `MSH-5` (receiving application) field is used for targeting
- Other categories still receive the message (e.g., labs get the patient even if targeting a specific insurer)

### 5. Transformation

For each route, the engine applies mapping rules to translate fields between formats:

| Rule Type | What It Does | Example |
|-----------|-------------|---------|
| `copy` | Direct field copy | `Patient-name[0].text` → `PID-5.1` |
| `map` | Value translation | `male` → `M`, `female` → `F` |
| `format` | Date/string formatting | `1990-02-22` → `19900222` |
| `concat` | Combine fields | First + Last → Full Name |
| `split` | Break apart | Full Name → First, Last |

### 6. Delivery

The transformed message is POSTed to the destination system with headers tracking the source (`Src-System-Id`) for round-trip routing. Up to 3 concurrent workers handle delivery per route.

### 7. Logging

Every message is logged in both the database (`Engine.logs` table) and rotating log files for full audit trail.

---

## Systems

### EHR — Electronic Health Record (Port 8001)

The hospital system. Manages patients, doctor visits, lab test ordering, vitals, billing, and insurance claims.

**Key capabilities:**
- Register patients (triggers FHIR bundle to engine → distributed to lab, insurer, patient portal)
- Create visit notes with diagnoses and complaints
- Order lab tests (routed to LIS via engine)
- Submit insurance claims (routed to Payer via engine)
- Receive lab results and claim decisions back from the engine

### LIS — Laboratory Information System (Port 8002)

The lab system. Receives test orders from hospitals, manages test workflows, and sends results back.

**Key capabilities:**
- Receive patient registrations and lab orders from the engine as HL7 messages
- Track test request lifecycle (pending → accepted → completed)
- Submit completed results as HL7 ORU^R01 messages back through the engine
- Multi-tenant: same patient NIC can exist at different labs (composite primary key)

### Payer — Insurance System (Port 8003)

The insurer system. Manages policies, patient eligibility, and claim adjudication.

**Key capabilities:**
- Receive patient registrations from the engine with policy information
- Manage insurance policies (medical, dental, vision, etc.)
- Review and approve/reject claims submitted by hospitals
- Send claim decisions (ACK^P03) back through the engine

### PHR — Personal Health Record (Port 8004)

The patient-facing portal. Gives patients read access to their medical data.

**Key capabilities:**
- Patient login and profile management
- View visit notes, lab results, and vitals shared by hospitals
- Receive FHIR bundles from the engine containing clinical data

### Interface Engine (Port 9000)

The central hub. Receives messages from any system, applies routing and transformation rules, and delivers to destinations.

**Key capabilities:**
- Register and manage connected systems (servers)
- Configure endpoints and routing rules with field-level mapping
- Translate between FHIR R4 and HL7 v2.x formats
- Park messages for offline destinations and auto-retry
- Full audit logging (database + rotating files)

---

## Message Flow Example

Here's what happens when a hospital registers a new patient:

```
 Hospital (EHR)                    Interface Engine                 Lab (LIS) / Insurer (Payer) / Patient (PHR)
      │                                  │                                    │
      │  POST /fhir/add-patient          │                                    │
      │  { FHIR Bundle with Patient      │                                    │
      │    + Coverage resources }         │                                    │
      │ ─────────────────────────────►    │                                    │
      │                                  │  1. Validate source system          │
      │                                  │  2. Extract FHIR paths              │
      │                                  │  3. Find matching routes            │
      │                                  │  4. Apply mapping rules             │
      │                                  │                                    │
      │                                  │  POST /get/new-patient (HL7)       │
      │                                  │ ──────────────────────────────►  LIS receives ADT^A01
      │                                  │                                    │  Saves patient with
      │                                  │  POST /get/registed_patient (HL7)  │  dest_system_id=EHR-1
      │                                  │ ──────────────────────────────►  Payer receives ADT^A04
      │                                  │                                    │  Saves patient + policy
      │                                  │  POST /fhir/receive-patient (FHIR) │
      │                                  │ ──────────────────────────────►  PHR receives Patient
      │                                  │                                    │
      │           200 OK                 │                                    │
      │ ◄─────────────────────────────   │                                    │
      │                                  │                                    │
      │  Patient saved to EHR DB         │                                    │
```

When the lab completes a test, results flow back through the engine to the originating hospital using the stored `dest_system_id` for targeted routing.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Web Framework** | FastAPI 0.124 |
| **ASGI Server** | Uvicorn 0.38 |
| **ORM** | SQLAlchemy 1.4 |
| **Migrations** | Alembic 1.17 |
| **Database** | Microsoft SQL Server (via pyodbc) |
| **FHIR Validation** | fhir.resources 8.2 (R4B) |
| **HL7 Parsing** | hl7 0.4.5, hl7apy 1.3.5 |
| **HTTP Client** | httpx 0.28 (async) |
| **Data Validation** | Pydantic 2.12 |
| **Rate Limiting** | slowapi 0.1.9 |
| **Load Testing** | Locust |

---

## Getting Started

### Prerequisites

- Python 3.9+
- Microsoft SQL Server (local or remote)
- ODBC Driver 17 for SQL Server

### 1. Clone the Repository

```bash
git clone https://github.com/Muhammad-Saaad/Health-FHIR-HL7-Processing-Engine-with-client-Simulator.git
cd Health-FHIR-HL7-Processing-Engine-with-client-Simulator
```

### 2. Create Virtual Environment & Install Dependencies

```bash
python -m venv health-venv

# Windows
health-venv\Scripts\activate

# Linux/Mac
source health-venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure the Database

Create five SQL Server databases: `EHR`, `LIS`, `Payer`, `Engine`, `PHR`.

Create a `.env` file in the project root:

```env
DATABASE_URL_EHR=mssql+pyodbc://@YOUR_SERVER/EHR?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes&Encrypt=no
DATABASE_URL_LIS=mssql+pyodbc://@YOUR_SERVER/LIS?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes&Encrypt=no
DATABASE_URL_Payer=mssql+pyodbc://@YOUR_SERVER/Payer?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes&Encrypt=no
DATABASE_URL_ENGINE=mssql+pyodbc://@YOUR_SERVER/Engine?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes&Encrypt=no
DATABASE_URL_PHR=mssql+pyodbc://@YOUR_SERVER/PHR?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes&Encrypt=no
```

Replace `YOUR_SERVER` with your SQL Server instance name (e.g., `DESKTOP-ABC\SQLEXPRESS`).

### 4. Run Database Migrations

```bash
cd EHR && alembic upgrade head && cd ..
cd LIS && alembic upgrade head && cd ..
cd Payer && alembic upgrade head && cd ..
cd InterfaceEngine && alembic upgrade head && cd ..
cd phr && alembic upgrade head && cd ..
```

### 5. Start the Services

Start each service in a separate terminal. **Start the Interface Engine first.**

```bash
# Terminal 1 — Interface Engine (start first)
cd InterfaceEngine
python main.py
# Runs on http://localhost:9000

# Terminal 2 — EHR (Hospital)
cd EHR
python main.py
# Runs on http://localhost:8001

# Terminal 3 — LIS (Lab)
cd LIS
python main.py
# Runs on http://localhost:8002

# Terminal 4 — Payer (Insurance)
cd Payer
python main.py
# Runs on http://localhost:8003

# Terminal 5 — PHR (Patient Portal)
cd phr
python main.py
# Runs on http://localhost:8004
```

### 6. Explore the APIs

Each service exposes interactive Swagger docs:

| Service | URL |
|---------|-----|
| EHR | http://localhost:8001/docs |
| LIS | http://localhost:8002/docs |
| Payer | http://localhost:8003/docs |
| PHR | http://localhost:8004/docs |
| Interface Engine | http://localhost:9000/docs |

---

## API Reference

### EHR (Port 8001)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/register-hospital` | Register a new hospital |
| `POST` | `/register-doctor` | Register a doctor |
| `POST` | `/patients` | Register a patient (triggers cross-system sync) |
| `GET` | `/patients/{patient_id}` | Get patient by ID |
| `GET` | `/all-patients/{hospital_id}` | List all patients at a hospital |
| `POST` | `/visit-note-add` | Create a visit note with optional lab orders |
| `POST` | `/submit-claims` | Submit an insurance claim |
| `GET` | `/lab-reports-by-{note_id}` | Get lab results for a visit |
| `POST` | `/fhir/receive-test-result` | Receive lab results from engine |
| `POST` | `/fhir/claim-response` | Receive claim decision from engine |

### LIS (Port 8002)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/SignUp` | Register lab staff |
| `GET` | `/get_patients/{lab_id}` | List patients at a lab |
| `GET` | `/requests/accepted/payment/paid/{lab_id}` | Billing reports |
| `POST` | `/results/complete` | Submit completed test results |
| `POST` | `/get/new-patient` | Receive patient from engine |
| `POST` | `/take_lab_order` | Receive test order from engine |

### Payer (Port 8003)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/signup` | Register insurer staff |
| `GET` | `/all_patients_per_policy_category/{category}/{id}` | Patients by policy type |
| `GET` | `/get_all_claims/{insurance_id}` | List all claims |
| `PUT` | `/change_claim_status/{claim_id}/{status}/user/{user_id}` | Approve/reject a claim |
| `POST` | `/get/registed_patient` | Receive patient from engine |
| `POST` | `/submit-claim` | Receive claim from engine |

### PHR (Port 8004)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/login` | Patient login |
| `GET` | `/visiting-notes/{nic}` | View visit history |
| `GET` | `/lab-reports/{note_id}` | View lab results |

### Interface Engine (Port 9000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/{path}` | Ingest a single message |
| `POST` | `/batch` | Ingest a batch of messages |
| `GET` | `/server` | List registered systems |
| `POST` | `/server` | Register a new system |
| `GET` | `/route` | List configured routes |
| `POST` | `/route` | Create a route with mapping rules |
| `GET` | `/logs` | Query message processing logs |

---

## Configuration

### Environment Variables (Interface Engine)

| Variable | Default | Description |
|----------|---------|-------------|
| `BATCH_CONCURRENCY` | 25 | Max parallel batch item processing |
| `ROUTE_WORKER_CONCURRENCY` | 3 | Workers per route |
| `DESTINATION_CONCURRENCY` | 3 | Parallel POSTs to same destination |
| `HTTP_READ_TIMEOUT` | 30s | HTTP client read timeout |
| `INGEST_AWAIT_TIMEOUT` | 40s | Max wait for all route workers |
| `INACTIVE_DEST_MAX_RETRIES` | 3 | Retry attempts for offline destinations |
| `INACTIVE_DEST_BACKOFF_SECS` | 20s | Delay between retries |
| `REDELIVERY_CHECK_INTERVAL` | 15s | Parked message check frequency |
| `BATCH_PRESERVE_ORDER` | true | Process batch items sequentially |
| `LOG_BACKUP_COUNT` | 7 | Days of log files to retain |

---

## Multi-Tenant Design

The system supports multiple organizations of each type running simultaneously with data isolation:

| System | Strategy | How It Works |
|--------|----------|-------------|
| **EHR** | `UNIQUE(hospital_id, nic)` | Same patient NIC can exist at different hospitals |
| **LIS** | Composite PK `(nic, lab_id)` | Same patient can be registered at multiple labs |
| **Payer** | Filtered `UNIQUE(insurance_id, nic)` | Same patient can have policies at different insurers |

Each system tracks a `dest_system_id` (the originating system) so responses can be routed back to the correct source — for example, when a lab sends results, they go back to the specific hospital that ordered the test.

### Running Multiple Instances

You can run multiple instances of the same system type (e.g., two hospitals) using separate environment files and ports:

```bash
# Hospital A
ENV_FILE=.env.hospital_a uvicorn EHR.main:app --port 8001

# Hospital B
ENV_FILE=.env.hospital_b uvicorn EHR.main:app --port 8011
```

---

## Resilience & Error Handling

### Park & Retry

If a destination system is offline when a message arrives, the engine doesn't drop it:

1. Message is **parked** in memory
2. A background `redelivery_watcher` checks every 15 seconds
3. When the destination comes back online, parked messages are automatically replayed
4. Configurable retry attempts (default: 3) with backoff (default: 20s)

### Transactional Consistency

If the engine fails to deliver a message, it returns a 502 error to the source system. The source system (e.g., EHR) catches this and **rolls back** its database transaction, ensuring data stays consistent across all systems.

### Health Checks

Each system exposes a `GET /health/{system_id}` endpoint. The Interface Engine periodically checks these to maintain an up-to-date status of all connected systems.

### Logging

| Log File | Content |
|----------|---------|
| `logs/main.log` | General application logs |
| `logs/main_mapping.log` | Mapping rule execution details |
| `logs/health_checks.log` | System health check results |
| `Engine.logs` table | Database audit trail (status, operation, messages) |

---

## Load Testing

The project includes a [Locust](https://locust.io/) configuration for load testing the Interface Engine:

```bash
pip install locust
locust -f locustfile.py --host=http://localhost:9000
```

Then open http://localhost:8089 to configure and run load tests.

---

## Project Structure

```
Health-FHIR-HL7-Processing-Engine-with-client-Simulator/
│
├── InterfaceEngine/                # Central message router & translator
│   ├── main.py                     # FastAPI app, ingestion, routing, workers
│   ├── models.py                   # Server, Endpoint, Route, MappingRule, Log models
│   ├── database.py                 # Database connection setup
│   ├── api/                        # API route handlers
│   │   ├── server.py               # Server registration & management
│   │   ├── endpoint.py             # Endpoint configuration
│   │   ├── route.py                # Route & mapping rule management
│   │   ├── logs.py                 # Log querying
│   │   └── user.py                 # Engine user authentication
│   ├── validation/                 # Format validation & extraction
│   │   ├── fhir_validation.py      # FHIR R4 validation & path extraction
│   │   └── hl7_validation.py       # HL7 v2 parsing & path extraction
│   └── alembic/                    # Database migrations
│
├── EHR/                            # Hospital system
│   ├── main.py                     # FastAPI app entry point
│   ├── model.py                    # Patient, Visit, LabReport, Bill models
│   ├── database.py                 # Database connection
│   ├── api/                        # API route handlers
│   │   ├── authentication.py       # Hospital & doctor auth
│   │   ├── patient.py              # Patient registration & FHIR bundle creation
│   │   ├── visit_note.py           # Visit notes & vitals
│   │   ├── lab.py                  # Lab test lookup (LOINC)
│   │   ├── claim.py                # Insurance claim submission
│   │   ├── engine_service.py       # Receive data from engine
│   │   └── config.py               # System configuration
│   └── alembic/                    # Database migrations
│
├── LIS/                            # Laboratory system
│   ├── main.py                     # FastAPI app entry point
│   ├── model.py                    # Lab, Patient, TestRequest, Result models
│   ├── database.py                 # Database connection
│   ├── api/                        # API route handlers
│   │   ├── auth.py                 # Lab staff authentication
│   │   ├── patient.py              # Patient management
│   │   ├── lab.py                  # Test request lifecycle
│   │   ├── results.py              # Result submission (ORU^R01)
│   │   ├── engine_service.py       # Receive orders from engine
│   │   └── config.py               # System configuration
│   └── alembic/                    # Database migrations
│
├── Payer/                          # Insurance system
│   ├── main.py                     # FastAPI app entry point
│   ├── models.py                   # Insurance, Policy, Claim models
│   ├── database.py                 # Database connection
│   ├── api/                        # API route handlers
│   │   ├── auth.py                 # Insurer staff authentication
│   │   ├── patient.py              # Patient & policy management
│   │   ├── policy.py               # Policy lookup
│   │   ├── claims.py               # Claim adjudication
│   │   ├── engine_service.py       # Receive claims from engine
│   │   └── config.py               # System configuration
│   └── alembic/                    # Database migrations
│
├── phr/                            # Patient portal
│   ├── main.py                     # FastAPI app entry point
│   ├── model.py                    # Patient, Visit, LabReport models
│   ├── database.py                 # Database connection
│   ├── api/                        # API route handlers
│   │   ├── authentication.py       # Patient login
│   │   ├── doctor.py               # Doctor lookup
│   │   ├── visit_note.py           # Visit history
│   │   ├── lab.py                  # Lab result viewing
│   │   └── engine_service.py       # Receive shared data from engine
│   └── alembic/                    # Database migrations
│
├── requirements.txt                # Python dependencies
├── .env                            # Database connection strings
└── locustfile.py                   # Load testing configuration
```

---

## License

This project is developed as an academic/research initiative for healthcare interoperability.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request
