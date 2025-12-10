from datetime import datetime
from pydantic import BaseModel, EmailStr


class SignUp(BaseModel):
    name: str
    email: EmailStr
    password: str
    date_join: str

    model_config = {"from_attributes": True}

class get_patient(BaseModel):
    patient_id : int
    cnic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: datetime | None
    address : str | None

    model_config = {"from_attributes": True}

class post_patient(BaseModel):
    cnic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: datetime | None
    address : str | None

    model_config = {"from_attributes": True}