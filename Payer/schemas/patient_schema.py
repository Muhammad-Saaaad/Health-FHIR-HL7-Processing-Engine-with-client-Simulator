from pydantic import BaseModel
from datetime import date

from schemas.policy_schema import patient_policy

class PatientCreate(BaseModel):
    name: str
    phone_no: str | None
    gender: str | None
    date_of_birth: date | None
    user_id: int | None
    insurance_type : str

class PatientDisplay(BaseModel):
    p_id: int
    mpi: int | None
    name: str
    gender: str | None
    date_of_birth: date | None
    phone_no: str | None
    policy_number: int | None

    model_config = {"from_attributes": True}

class PatientPolicyDetails(BaseModel):
    p_id: int
    name: str
    cnic: str
    date_of_birth: date | None

    patient_policy : list[patient_policy]

