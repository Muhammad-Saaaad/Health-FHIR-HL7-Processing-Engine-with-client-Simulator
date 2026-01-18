from pydantic import BaseModel
from datetime import date

class patient_policy(BaseModel):
    policy_id: int
    category_name: str
    total_coverage: float
    amount_used : float
    description: str | None

class PolicyCreate(BaseModel):
    p_id: int
    u_id: int
    category_name: str
    total_coverage: float
    amount_used: float = 0.0
    description: str | None
