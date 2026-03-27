import os

import csv
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from model import LoincMaster # your models file, make sure it includes LoincMaster
# from model import Base, LoincMaster  # your models file

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL_EHR"), echo=False, future=True)

LOINC_CSV_PATH = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\EHR\Loinc_extraction\Loinc.csv"  # Update this path to your actual CSV file location

def import_loinc(csv_path: str):
    rows_imported = 0
    rows_skipped = 0
    batch = []
    BATCH_SIZE = 500

    LAB_CLASSES = {
        'CHEM', 'HEM/BC', 'MICRO', 'UA', 'COAG',
        'SERO', 'DRUG/TOX', 'IMMUN', 'ALLERGY',
        'FERT', 'HLA', 'MOLPATH', 'PATH', 'TUMOR'
    }

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # filter: active only, orderable only
            if row.get("STATUS") != "ACTIVE":
                rows_skipped += 1
                continue
            if row.get("ORDER_OBS") not in ("Order", "Both"):
                rows_skipped += 1
                continue
            if row.get("CLASS") not in LAB_CLASSES:
                rows_skipped += 1
                continue

            batch.append({
                "loinc_code":       row["LOINC_NUM"],
                "long_common_name": row["LONG_COMMON_NAME"],
                "short_name":       row.get("SHORTNAME") or None,
                "component":        row.get("COMPONENT") or None,
                "system":           row.get("SYSTEM") or None,
            })

            # insert in batches of 500 for performance
            if len(batch) >= BATCH_SIZE:
                _upsert_batch(batch)
                rows_imported += len(batch)
                batch.clear()
                print(f"  imported {rows_imported} so far...")

    # insert remaining rows
    if batch:
        _upsert_batch(batch)
        rows_imported += len(batch)

    print(f"\nDone. Imported: {rows_imported} | Skipped: {rows_skipped}")


def _upsert_batch(batch: list[dict]):
    with Session(engine) as session:
        for item in batch:
            existing = session.get(LoincMaster, item["loinc_code"])
            if existing:
                # update name in case it changed in this release
                existing.long_common_name = item["long_common_name"]
                existing.short_name       = item["short_name"]
            else:
                session.add(LoincMaster(
                    loinc_code       = item["loinc_code"],
                    long_common_name = item["long_common_name"],
                    short_name       = item["short_name"],
                    component        = item["component"],
                    system           = item["system"],
                ))
        session.commit()


if __name__ == "__main__":
    print("Starting LOINC import...")
    import_loinc(LOINC_CSV_PATH)