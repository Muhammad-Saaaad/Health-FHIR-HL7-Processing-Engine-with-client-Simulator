from pydantic import BaseModel
from datetime import date

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
