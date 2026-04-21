from datetime import datetime
from pydantic import BaseModel, field_serializer

class LabReport(BaseModel):
    report_id : int
    visit_id : int

    lab_name: str
    test_name : str
    test_status: str
    created_at : datetime | None
    updated_at : datetime | None

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return datetime.strftime(value, "%Y-%m-%d %H:%M %p")
    
    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return datetime.strftime(value, "%Y-%m-%d %H:%M %p")

    model_config = {"from_attributes": True}

class LoincMaster(BaseModel):
    loinc_code: str
    long_common_name: str
    short_name: str | None
    component: str | None
    system: str | None

    model_config = {"from_attributes": True}
