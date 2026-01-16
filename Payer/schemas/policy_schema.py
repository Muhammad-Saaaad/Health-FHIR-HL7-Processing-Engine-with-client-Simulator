from pydantic import BaseModel
from datetime import date

class patient_policy(BaseModel):
    policy_id: int
    category_name: str
    total_coverage: float
    amount_used : float
    description: str | None

class PatientPolicyDetails(BaseModel):
    p_id: int
    name: str
    cnic: str
    date_of_birth: date | None

    patient_policy : list[patient_policy]

class PolicyCreate(BaseModel):
    p_id: int
    u_id: int
    category_name: str
    total_coverage: float
    amount_used: float = 0.0
    description: str | None
