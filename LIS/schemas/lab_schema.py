from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, date

class TestRequestCreate(BaseModel):
    patient_cnic: str
    test_name: str = Field(..., max_length=50)

# --- Schema for Test Request Status Update ---
class TestRequestStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(Pending|Accepted|Declined|Completed)$")
    decline_reason: str | None

class TestRequestOut(BaseModel):
    patient_id : int
    test_name: str
    status: str
    decline_reason: str | None
    locked_by: int | None
    locked_at: datetime | None

    model_config = {"from_attributes": True}

class MiniTestCreate(BaseModel):
    """Schema for a single mini-test result input."""
    test_name: str
    normal_range: str
    result_value: str

class MiniTestOut(MiniTestCreate):
    """Schema for returning a single mini-test result."""
    mini_test_id: int
    result_id: int # Foreign key to TestResult
    
    model_config = {"from_attributes":True}

class CompleteTestResultCreate(BaseModel):
    user_id: int
    test_req_id: int
    description: str| None = None
    mini_tests: list[MiniTestCreate] # Nested list of mini-tests

class TestResultOut(BaseModel):
    result_id: int
    user_id: int
    test_req_id: int
    description: str | None
    mini_test_results: list[MiniTestOut] = []
    
    model_config = {"from_attributes":True}
