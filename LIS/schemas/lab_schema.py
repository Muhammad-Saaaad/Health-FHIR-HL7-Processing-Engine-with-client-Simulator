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
    mpi : int
    test_name: str
    status: str
    locked_by: int | None
    locked_at: datetime | None

    model_config = {"from_attributes": True}