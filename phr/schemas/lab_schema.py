from datetime import datetime

from pydantic import BaseModel, field_serializer

class LabReportBase(BaseModel):
    report_id: int
    lab_name: str
    test_name: str
    updated_at: datetime | None = None
    test_status: str | None

    @field_serializer("updated_at")
    def format_updated_at(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M %p")
    
    @field_serializer("test_status")
    def format_test_status(self, value: str) -> str:
        if value is None:
            return "Pending"
        return value

    model_config = {"from_attributes": True}

class LabMiniTestResult(BaseModel):
    mini_test_id: int
    test_name: str
    normal_range: str
    result_value: str

class LabResult(BaseModel):
    report_id: int

    test_name: str
    description: str | None
    mini_test_results: list[LabMiniTestResult] | None    
