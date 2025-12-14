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

class BillingCreate(BaseModel):
    pid: int
    test_req_id: int
    bill_amount: float

class BillingOut(BillingCreate):
    bill_id: int
    payment_status: str
    create_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes":True}