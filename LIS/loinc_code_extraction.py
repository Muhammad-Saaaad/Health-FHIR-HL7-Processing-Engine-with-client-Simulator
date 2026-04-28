import os
import csv
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from model import LoincMaster

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL_LIS"), echo=False, future=True)

LOINC_CSV_PATH = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\LIS\Loinc.csv"

def import_loinc(csv_path: str):
    rows_imported = 0
    rows_skipped  = 0
    batch         = []
    BATCH_SIZE    = 500

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Filter 1: active only
            if row.get("STATUS") != "ACTIVE":
                rows_skipped += 1
                continue

            # Filter 2: orderable only
            if row.get("ORDER_OBS") not in ("Order", "Both"):
                rows_skipped += 1
                continue

            # ✅ No CLASS filter — let all lab-orderable codes through
            # The CLASS column is stored so you can filter later in queries

            batch.append({
                "loinc_code":       row["LOINC_NUM"],
                "long_common_name": row["LONG_COMMON_NAME"],
                "short_name":       row.get("SHORTNAME")   or None,
                "component":        row.get("COMPONENT")   or None,
                "system":           row.get("SYSTEM")      or None,
                # ✅ Now saving these fields too
                "class_":           row.get("CLASS")       or None,
                "order_obs":        row.get("ORDER_OBS")   or None,
                "scale_typ":        row.get("SCALE_TYP")   or None,
            })

            if len(batch) >= BATCH_SIZE:
                _upsert_batch(batch)
                rows_imported += len(batch)
                batch.clear()
                print(f"  imported {rows_imported} so far...")

    if batch:
        _upsert_batch(batch)
        rows_imported += len(batch)

    print(f"\nDone. Imported: {rows_imported} | Skipped: {rows_skipped}")


def _upsert_batch(batch: list[dict]):
    """
    Bulk upsert — one query per batch, not one per row.
    Uses MS SQL MERGE behaviour via SQLAlchemy's bulk approach.
    """
    with Session(engine) as session:
        # Separate into new vs existing in one shot using bulk logic
        loinc_codes = [item["loinc_code"] for item in batch]

        # Fetch all existing codes in this batch in ONE query
        existing_codes = set(
            code for (code,) in session.query(LoincMaster.loinc_code)
            .filter(LoincMaster.loinc_code.in_(loinc_codes))
            .all()
        )

        to_insert = []
        to_update = []

        for item in batch:
            if item["loinc_code"] in existing_codes:
                to_update.append(item)
            else:
                to_insert.append(item)

        # Bulk insert new rows
        if to_insert:
            session.bulk_insert_mappings(LoincMaster, to_insert)

        # Bulk update existing rows
        if to_update:
            session.bulk_update_mappings(LoincMaster, [
                {
                    "loinc_code":       item["loinc_code"],
                    "long_common_name": item["long_common_name"],
                    "short_name":       item["short_name"],
                    "class_":           item["class_"],
                    "order_obs":        item["order_obs"],
                    "scale_typ":        item["scale_typ"],
                }
                for item in to_update
            ])

        session.commit()


if __name__ == "__main__":
    print("Starting LOINC import...")
    import_loinc(LOINC_CSV_PATH)