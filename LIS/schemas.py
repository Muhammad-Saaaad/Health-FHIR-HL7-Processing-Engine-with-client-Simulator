from pydantic import BaseModel, Field
from datetime import datetime

# --- Base Schema for Patient Input ---
class PatientBase(BaseModel):
    cnic: str = Field(..., max_length=20)
    fname: str = Field(..., max_length=25)
    lname: str | None
    dob: datetime | None
    gender: str = Field(..., max_length=10)
    phone: str | None
    dignosis: str | None

# --- Schema for Patient Creation ---
class PatientCreate(PatientBase):
    pass

# --- Schema for Patient Output (Response) ---
class PatientOut(PatientBase):
    pid: int
    created_at: datetime

    model_config = {"from_attributes": True}

# --- Schema for Test Request Input ---
class TestRequestCreate(BaseModel):
    patient_id: int
    test_name: str = Field(..., max_length=50)

# --- Schema for Test Request Status Update ---
class TestRequestStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(Pending|Accepted|Declined|Completed)$")
    decline_reason: str | None

# --- Schema for Test Request Output (Response) ---
class TestRequestOut(TestRequestCreate):
    test_req_id: int
    status: str
    decline_reason: str | None
    locked_by: int | None
    locked_at: datetime | None

    class Config:
        from_attributes = True