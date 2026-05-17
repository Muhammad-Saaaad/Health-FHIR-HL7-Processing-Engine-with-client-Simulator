from pydantic import BaseModel, field_serializer
from datetime import date

from schemas.policy_schema import patient_policy

class PatientCreate(BaseModel):
    nic: str | None = None
    name: str
    phone_no: str | None
    gender: str | None
    date_of_birth: date | None
    user_id: int | None
    insurance_type : str

class PatientDisplay(BaseModel):
    p_id: int
    nic: str | None
    name: str
    gender: str | None
    date_of_birth: date | None
    phone_no: str | None
    policy_number: int | None

    @field_serializer("date_of_birth")
    def serialize_date_of_birth(self, dob: date | None) -> str | None:
        try:
            if dob is None:
                return None
            return dob.strftime("%B %d, %Y")
        except Exception as e:
            print(f"Error serializing date_of_birth: {str(e)}")
            return dob

    model_config = {"from_attributes": True}

class PatientPolicyDetails(BaseModel):
    p_id: int
    nic: str | None
    name: str
    Age: str | date | None
    phone_no: str | None
    gender: str | None

    # patient_policy : list[patient_policy]
    patient_policy : patient_policy

    @field_serializer("Age")
    def serialize_age(self, age_date: date | None) -> str | None:
        if age_date is None:
            return None
        today = date.today()
        age = today.year - age_date.year - ((today.month, today.day) < (age_date.month, age_date.day))
        return str(age)
