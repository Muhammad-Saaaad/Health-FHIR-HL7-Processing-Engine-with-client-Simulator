import os
import csv
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from model import LabTest

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL_LIS"), echo=False, future=True)

LABTEST_CSV_PATH = os.path.join(os.path.dirname(__file__), "labTests.csv")

_HEADER_MAP = {
    "test code": "test_code",
    "test name": "test_name",
    "parameter": "parameter",
    "unit": "unit",
    "gender": "gender",
    "age >= 18 (adults)": "adult_range",
    "age < 18 (pediatric)": "child_range",
    "age <18 (pediatric)": "child_range",
}

def _normalize_header(text: str) -> str:
    if text is None:
        return ""
    cleaned = text.strip().lower()
    cleaned = cleaned.replace("\ufeff", "")
    cleaned = cleaned.replace("\u2265", ">=")
    cleaned = cleaned.replace("\u2013", "-")
    cleaned = " ".join(cleaned.split())
    return cleaned

def import_lab_tests(csv_path: str):
    rows_imported = 0
    rows_skipped  = 0
    batch         = []
    BATCH_SIZE    = 500

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        with Session(engine) as session:
            existing = set(
                session.query(
                    LabTest.test_code,
                    LabTest.test_name,
                    LabTest.parameter,
                    LabTest.gender,
                    LabTest.unit,
                    LabTest.adult_range,
                    LabTest.child_range,
                ).all()
            )

            for row in reader:
                normalized = {}
                for key, value in row.items():
                    mapped = _HEADER_MAP.get(_normalize_header(key))
                    if not mapped:
                        continue
                    normalized[mapped] = (value or "").strip() or None

                if not normalized.get("test_code") or not normalized.get("test_name"):
                    rows_skipped += 1
                    continue

                batch.append({
                    "test_code": normalized.get("test_code"),
                    "test_name": normalized.get("test_name"),
                    "parameter": normalized.get("parameter"),
                    "unit": normalized.get("unit"),
                    "gender": normalized.get("gender"),
                    "adult_range": normalized.get("adult_range"),
                    "child_range": normalized.get("child_range"),
                })

                if len(batch) >= BATCH_SIZE:
                    rows_imported += _insert_batch(session, batch, existing)
                    batch.clear()
                    print(f"  imported {rows_imported} so far...")

            if batch:
                rows_imported += _insert_batch(session, batch, existing)

    print(f"\nDone. Imported: {rows_imported} | Skipped: {rows_skipped}")


def _insert_batch(session: Session, batch: list[dict], existing: set[tuple]):
    """Bulk insert rows that do not already exist in the table."""
    to_insert = []
    for item in batch:
        key = (
            item.get("test_code"),
            item.get("test_name"),
            item.get("parameter"),
            item.get("gender"),
            item.get("unit"),
            item.get("adult_range"),
            item.get("child_range"),
        )
        if key in existing:
            continue
        existing.add(key)
        to_insert.append(item)

    if to_insert:
        session.bulk_insert_mappings(LabTest, to_insert)
        session.commit()
    return len(to_insert)


if __name__ == "__main__":
    print("Starting LabTest import...")
    import_lab_tests(LABTEST_CSV_PATH)