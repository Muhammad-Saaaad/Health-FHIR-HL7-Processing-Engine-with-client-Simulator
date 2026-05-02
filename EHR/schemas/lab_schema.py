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
    
    @field_serializer("test_status")
    def serialize_test_status(self, value: str) -> str:
        if value is None or value is "Ordered":
            return "Pending"
        if value is "Arrived":
            return "Completed"
        if value in ["Cancelled", "Rejected", "Declined", "Decline", "declined", "decline"]:
            return "Rejected"
        
        return value.capitalize()
    
    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return datetime.strftime(value, "%Y-%m-%d %H:%M %p")

    model_config = {"from_attributes": True}

class LabMiniTestResult(BaseModel):
    mini_test_id: int
    test_name: str
    normal_range: str
    unit: str
    result_value: str

class LabResult(BaseModel):
    report_id: int

    test_name: str
    description: str | None
    mini_test_results: list[LabMiniTestResult] | None

class LoincMaster(BaseModel):
    loinc_code: str
    long_common_name: str
    short_name: str | None = None
    component: str | None = None
    system: str | None = None
    display_name: str | None = None
    mobile_name: str | None = None

    model_config = {"from_attributes": True}
