from pydantic import BaseModel

class PolicyCreate(BaseModel):
    p_id: int
    u_id: int
    category_name: str
    total_coverage: float
    amount_used: float = 0.0
    description: str | None

class patient_policy(BaseModel):
    policy_id: int
    policy_plan: str # category_name in the database
    total_coverage: float
    amount_used : float
    # description: str | None
    status: str