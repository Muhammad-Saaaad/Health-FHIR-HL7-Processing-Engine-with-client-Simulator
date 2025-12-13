from pydantic import BaseModel, EmailStr
from datetime import date

class SystemUserCreate(BaseModel):
    user_name: str
    email: EmailStr
    password: str  

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SystemUserDisplay(BaseModel):
    user_id: int
    user_name: str
    email: EmailStr

    model_config = {"from_attributes": True}

class PatientCreate(BaseModel):
    name: str
    cnic: str
    phone_no: str | None
    gender: str | None
    date_of_birth: date | None
    user_id: int | None

class PatientDisplay(BaseModel):
    p_id: int
    name: str
    cnic: str
    date_of_birth: date | None
    user_id: int | None

    model_config = {"from_attributes": True}


class PolicyCreate(BaseModel):
    p_id: int
    u_id: int
    category_name: str
    total_coverage: float
    amount_used: float = 0.0
    description: str | None
    status: str


class PatientClaimCreate(BaseModel):
    claim_id: int
    policy_id: int
    service_name: str
    bill_amount: float
    provider_phone_no: str | None =  None
    item_status: str

class PatientClaimDisplay(BaseModel):
    claim_id: int
    service_name: str
    bill_amount: float
    item_status: str

    model_config = {"from_attributes": True}