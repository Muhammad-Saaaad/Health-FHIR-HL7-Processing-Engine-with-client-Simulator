from datetime import date, datetime
from pydantic import BaseModel, field_serializer

class get_patient(BaseModel):
    mpi : int
    name : str
    phone_no : str | None
    gender : str

    model_config = {"from_attributes": True}

class SpecificPatient(get_patient):
    age: date | str
    nic : str
    address : str | None

    @field_serializer("age")
    def serialize_age(self, value: date):
        today_date = datetime.now().date()
        age = today_date.year - value.year - ((today_date.month, today_date.day) < (value.month, value.day))
        return age

class post_patient(BaseModel):
    nic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: date | str
    address : str | None
    insurance_company: str
    policy_number: int
    plan_type: str

    @field_serializer("date_of_birth")
    def serialize_date_of_birth(self, value: str):
        return datetime.strptime(value, "%Y-%m-%d").date()

    model_config = {"from_attributes": True}