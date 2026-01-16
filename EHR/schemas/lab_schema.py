from datetime import datetime
from pydantic import BaseModel

class LabReport(BaseModel):
    report_id : int
    visit_id : int

    lab_name: str
    test_name : str
    test_status: str
    created_at : datetime | None
    updated_at : datetime | None