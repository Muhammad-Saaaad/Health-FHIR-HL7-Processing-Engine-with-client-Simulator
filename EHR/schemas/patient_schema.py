from datetime import date, datetime
from pydantic import BaseModel, field_serializer, field_validator

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
    hospital_id: int
    nic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: date | str
    address : str | None
    insurance_company: str
    policy_number: int
    plan_type: str

    @field_validator("date_of_birth", mode="before")
    def validate_dob(cls, value):
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("date_of_birth must be in YYYY-MM-DD format")
        
        if not isinstance(value, date):
            raise ValueError("date_of_birth must be a date object or a string in YYYY-MM-DD format")
        
        if value > datetime.now().date():
            raise ValueError("date_of_birth cannot be in the future")
        
        return value

    @field_serializer("date_of_birth")
    def serialize_date_of_birth(self, value: str):
        return datetime.strptime(value, "%Y-%m-%d").date()

    model_config = {"from_attributes": True}