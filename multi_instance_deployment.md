# Multi-Instance Deployment Guide
> One codebase — multiple hospital instances, each with its own database and frontend.

---

## Backend (FastAPI + SQLAlchemy)

### Core Concept
One codebase, four different `.env` files, each pointing to a different database. The server reads which database to connect to at startup. **Do not copy the code 4 times.**

---

### Step 1 — Read DB URL from environment

```python
# database.py
import os
from dotenv import load_dotenv

# reads ENV_FILE from the shell environment, defaults to .env
env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(env_file)

engine = create_engine(os.getenv("DATABASE_URL"))
```

---

### Step 2 — Create 4 separate `.env` files

```bash
# .env.hospital_a
DATABASE_URL=mssql+pyodbc://user:pass@server/HospitalA_DB?driver=ODBC+Driver+17+for+SQL+Server
APP_PORT=8001
HOSPITAL_NAME=Insurance Hospital A

# .env.hospital_b
DATABASE_URL=mssql+pyodbc://user:pass@server/HospitalB_DB?driver=ODBC+Driver+17+for+SQL+Server
APP_PORT=8002
HOSPITAL_NAME=Hospital B

# .env.hospital_c
DATABASE_URL=mssql+pyodbc://user:pass@server/HospitalC_DB?driver=ODBC+Driver+17+for+SQL+Server
APP_PORT=8003
HOSPITAL_NAME=Hospital C

# .env.hospital_d
DATABASE_URL=mssql+pyodbc://user:pass@server/HospitalD_DB?driver=ODBC+Driver+17+for+SQL+Server
APP_PORT=8004
HOSPITAL_NAME=Hospital D
```

---

### Step 3 — Run each instance pointing to its own env file

```bash
# terminal 1 — Hospital A
ENV_FILE=.env.hospital_a uvicorn main:app --port 8001

# terminal 2 — Hospital B
ENV_FILE=.env.hospital_b uvicorn main:app --port 8002

# terminal 3 — Hospital C
ENV_FILE=.env.hospital_c uvicorn main:app --port 8003

# terminal 4 — Hospital D
ENV_FILE=.env.hospital_d uvicorn main:app --port 8004
```

---

### Step 4 — Run Alembic migrations per instance

Make sure `alembic/env.py` reads from the env file:

```python
# alembic/env.py
import os
from dotenv import load_dotenv

env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(env_file)

config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))
```

Then run migrations against each database separately:

```bash
ENV_FILE=.env.hospital_a alembic upgrade head
ENV_FILE=.env.hospital_b alembic upgrade head
ENV_FILE=.env.hospital_c alembic upgrade head
ENV_FILE=.env.hospital_d alembic upgrade head
```

---

### Backend Instance Map

| Instance | Port | Database | Env file |
|---|---|---|---|
| Insurance Hospital A | 8001 | HospitalA_DB | .env.hospital_a |
| Hospital B | 8002 | HospitalB_DB | .env.hospital_b |
| Hospital C | 8003 | HospitalC_DB | .env.hospital_c |
| Hospital D | 8004 | HospitalD_DB | .env.hospital_d |

---
---

## Frontend (React + Vite)

### Core Concept
Environment variables are baked in at **build time** in React. You build 4 separate bundles, each talking to a different backend instance. One codebase, four deployments.

---

### Step 1 — Use env variable for API URL

```jsx
// api.js
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL      // Vite
// or
// const BASE_URL = process.env.REACT_APP_API_URL  // Create React App

export const api = axios.create({ baseURL: BASE_URL })
```

---

### Step 2 — Create 4 env files

```bash
# .env.hospital_a
VITE_API_URL=http://localhost:8001
VITE_HOSPITAL_NAME=Insurance Hospital A

# .env.hospital_b
VITE_API_URL=http://localhost:8002
VITE_HOSPITAL_NAME=Hospital B

# .env.hospital_c
VITE_API_URL=http://localhost:8003
VITE_HOSPITAL_NAME=Hospital C

# .env.hospital_d
VITE_API_URL=http://localhost:8004
VITE_HOSPITAL_NAME=Hospital D
```

---

### Step 3 — Build 4 separate bundles

Vite automatically picks up `.env.hospital_a` when `--mode hospital_a` is passed:

```bash
vite build --mode hospital_a --outDir dist/hospital_a
vite build --mode hospital_b --outDir dist/hospital_b
vite build --mode hospital_c --outDir dist/hospital_c
vite build --mode hospital_d --outDir dist/hospital_d
```

---

### Step 4 — Run in development on different ports

```bash
# terminal 1
vite --mode hospital_a --port 3001

# terminal 2
vite --mode hospital_b --port 3002

# terminal 3
vite --mode hospital_c --port 3003

# terminal 4
vite --mode hospital_d --port 3004
```

---

### Step 5 — Show hospital name in the UI (optional)

```jsx
const HospitalName = import.meta.env.VITE_HOSPITAL_NAME

const Navbar = () => (
  <nav>
    <h1>{HospitalName}</h1>  {/* shows "Insurance Hospital A" etc. */}
  </nav>
)
```

---

### Frontend Instance Map

| Frontend port | Backend port | Database | Env mode |
|---|---|---|---|
| 3001 | 8001 | HospitalA_DB | hospital_a |
| 3002 | 8002 | HospitalB_DB | hospital_b |
| 3003 | 8003 | HospitalC_DB | hospital_c |
| 3004 | 8004 | HospitalD_DB | hospital_d |

---

## Summary

| | Backend | Frontend |
|---|---|---|
| Config file | `.env.hospital_x` | `.env.hospital_x` |
| How it's loaded | `ENV_FILE=.env.hospital_x uvicorn ...` | `vite --mode hospital_x` |
| Isolation | Separate database per instance | Separate build bundle per instance |
| Code changes | Apply to all instances automatically | Rebuild all bundles to apply |
| Migration | Run `alembic upgrade head` per instance | N/A |
