# Making Visit Note API Async

## Overview

There are **3 layers** you need to make async — the route, the database session, and the engine HTTP call. Missing any one of them means you're still blocking.

---

## Layer 1 — The Route Itself

Simply add `async def` to your route functions:

```python
@router.post("/visit-note-add", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_visit_note(visit_note: schema.VisitNote, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
```

---

## Layer 2 — Async SQLAlchemy Session

This is the most important change. Your current `get_db` uses a regular synchronous session — that blocks the entire thread while waiting for the DB. You need `AsyncSession`:

```python
# database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Change your connection string driver:
# mssql+pyodbc://  →  mssql+aioodbc://
engine = create_async_engine(
    "mssql+aioodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server",
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

Install the async driver:

```bash
pip install aioodbc
```

---

## Layer 3 — Async Engine HTTP Call

Your `send_visit_note_to_engine` is currently a blocking `requests` call. Replace with `httpx`:

```python
# engine_service.py
import httpx

async def send_visit_note_to_engine(payload: dict) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "http://your-engine-url/receive",
                json=payload
            )
            response.raise_for_status()
            return "sucessfull"
        except httpx.HTTPStatusError as e:
            return f"engine error: {e.response.status_code}"
        except httpx.RequestError as e:
            return f"connection error: {str(e)}"
```

Install it:

```bash
pip install httpx
```

---

## Full Updated Route

With all three layers applied together:

```python
from sqlalchemy.ext.asyncio import AsyncSession

@router.post("/visit-note-add", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_visit_note(
    visit_note: schema.VisitNote,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    try:
        logger.info(f"Received request for patient MPI: {visit_note.mpi}")

        new_bill = model.Bill(
            insurance_amount=visit_note.bill_amount,
            bill_status=False,
        )
        db.add(new_bill)
        await db.flush()  # ← await all DB operations

        bill_id = new_bill.bill_id

        # ── Validate patient and doctor ──────────────────
        patient = await db.get(model.Patient, visit_note.mpi)
        if not patient:
            raise HTTPException(status_code=400, detail="Invalid patient MPI")

        result = await db.execute(
            select(model.Doctor).where(model.Doctor.doctor_id == visit_note.doctor_id)
        )
        is_doctor = result.scalar_one_or_none()
        if not is_doctor:
            raise HTTPException(status_code=400, detail="Invalid doctor ID")

        # ── Create visit note ────────────────────────────
        new_visit_note = model.VisitingNotes(
            mpi=visit_note.mpi,
            doctor_id=visit_note.doctor_id,
            bill_id=bill_id,
            note_title=visit_note.note_title,
            patient_complaint=visit_note.patient_complaint,
            dignosis=visit_note.dignosis,
            note_details=visit_note.note_details,
        )
        db.add(new_visit_note)
        await db.flush()

        # ── Build FHIR message ───────────────────────────
        unique_id = str(uuid4())
        patient_visit = { ... }  # same as your existing FHIR build

        # ── Process lab tests if provided ────────────────
        if visit_note.test_names and visit_note.lab_name:
            is_success, patient_visit = await get_test_report(
                unique_id=unique_id,
                fhir_message=patient_visit,
                visit_id=new_visit_note.note_id,
                mpi=visit_note.mpi,
                lab_name=visit_note.lab_name,
                test_details=visit_note.test_names,
                db=db
            )
            if not is_success:
                raise HTTPException(status_code=400, detail="Failed to process lab tests")

        # ── Send to engine ───────────────────────────────
        success_message = await send_visit_note_to_engine(patient_visit)  # ← await

        if success_message == "sucessfull":
            await db.commit()
            logger.info(f"Visit note {new_visit_note.note_id} committed successfully")
        else:
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"Engine sync failed: {success_message}")

        return {"message": "data inserted sucessfully"}

    except Exception as exp:
        await db.rollback()
        logger.error(f"Error: {str(exp)}")
        raise HTTPException(status_code=400, detail=str(exp))
```

---

## Async Version of `get_test_report`

```python
async def get_test_report(
    unique_id: str,
    fhir_message: dict,
    visit_id: int,
    mpi: int,
    lab_name: str,
    test_details: list[lab_schema.LoincMaster],
    db: AsyncSession
) -> tuple[bool, dict]:

    from sqlalchemy import select

    lab_reports = []
    for test_detail in test_details:
        result = await db.execute(
            select(model.LoincMaster).where(
                model.LoincMaster.loinc_code == test_detail.loinc_code
            )
        )
        loinc_entry = result.scalar_one_or_none()
        if not loinc_entry:
            raise HTTPException(
                status_code=400,
                detail=f"LOINC code {test_detail.loinc_code} not found"
            )

        lab_reports.append(model.LabReport(
            visit_id=visit_id,
            loinc_code=test_detail.loinc_code,
            lab_name=lab_name,
            test_name=loinc_entry.display_name,
        ))
        fhir_message["entry"].append({ ... })  # same ServiceRequest build

    db.add_all(lab_reports)
    await db.flush()
    return True, fhir_message
```

---

## Quick Reference — Sync vs Async

The rule is simple — **every DB call and every network call needs `await`**.

| Old (sync) | New (async) |
|---|---|
| `db.flush()` | `await db.flush()` |
| `db.commit()` | `await db.commit()` |
| `db.rollback()` | `await db.rollback()` |
| `db.get(Model, id)` | `await db.get(Model, id)` |
| `db.query(Model).filter().first()` | `await db.execute(select(Model).where(...))` then `.scalar_one_or_none()` |
| `requests.post(...)` | `await client.post(...)` with `httpx.AsyncClient` |

---

## Result

With these changes, FastAPI will handle 50–60 simultaneous visit note requests without any of them blocking each other — each one awaits its DB and HTTP operations independently on the event loop.
