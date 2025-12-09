from datetime import datetime
from pydantic import BaseModel, EmailStr

class fetchDoctors(BaseModel):
    doctor_id : int
    name: str
    email: EmailStr
    password: str
    specialization: str
    phone_no: str
    date_join: datetime
    about: str

    model_config = {"from_attributes": True}