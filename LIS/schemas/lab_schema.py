from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, date

class LabBase(BaseModel):
    report_id: int | None = None
    test_name: str | None = None
    vid: str | None = None
    status: str | None = None

class TestRequestCreate(BaseModel):
    patient_cnic: str
    test_name: str = Field(..., max_length=50)

# --- Schema for Test Request Status Update ---
class TestRequestStatusUpdate(BaseModel):
    req_id_status: dict[int, str] # Mapping of request IDs to their new statuses
    req_id_bill: dict[int, float] # Mapping of request IDs to their bills. 
    user_id: int
    visit_id: str
    # status: str = Field(..., pattern="^(Pending|Accepted|Declined|Completed)$")

class TestRequestOut(BaseModel):
    test_req_id: int
    nic: str
    test_name: str
    status: str
    locked_by: int | None
    locked_at: datetime | None

    model_config = {"from_attributes": True}

# class ShowLabTestParams(BaseModel):
    

class LabTestBase(BaseModel):
    test_id: int
    test_code: str

    test_name : str 
    parameter :  str | None
    unit : str | None
    test_range : str | None

class MiniLabResults(BaseModel):
    mini_test_name: str
    normal_range: str
    unit: str
    value: str


class MiniLabResultOut(BaseModel):
    mini_test_id: int
    result_id: int
    mini_test_name: str
    normal_range: str
    unit: str
    result_value: str

    model_config = {"from_attributes": True}
class LabTestCreate(BaseModel):
    user_id: int
    nic: str
    test_req_id: int

    description: str | None = None
    mini_test: list[MiniLabResults] | None = None


class LabResultOut(BaseModel):
    result_id: int
    user_id: int
    test_req_id: int
    description: str | None
    created_at: datetime
    mini_test: list[MiniLabResultOut] = []

    model_config = {"from_attributes": True}
