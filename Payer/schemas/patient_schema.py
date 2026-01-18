from pydantic import BaseModel
from datetime import date

from schemas.policy_schema import patient_policy

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

class PatientPolicyDetails(BaseModel):
    p_id: int
    name: str
    cnic: str
    date_of_birth: date | None

    patient_policy : list[patient_policy]

