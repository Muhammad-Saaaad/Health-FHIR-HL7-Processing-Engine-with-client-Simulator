from pydantic import BaseModel
from datetime import datetime

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