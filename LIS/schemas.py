from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, date

class SignUp(BaseModel):
    user_name: str
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}
class Login(BaseModel):
    email: EmailStr
    password: str

class PatientBase(BaseModel):
    cnic: str = Field(..., max_length=20)
    fname: str = Field(..., max_length=25)
    lname: str | None
    dob: datetime | None
    gender: str = Field(..., max_length=10)
    phone: str | None
    dignosis: str | None

# --- Schema for Patient Creation ---
class Patient(PatientBase):
    pid: int
    cnic : str
    fname : str
    lname : str | None
    dob : datetime | date | None
    gender : str
    phone : str
    dignosis : str
    created_at : datetime | date | None

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

    model_config = {"from_attributes": True}
