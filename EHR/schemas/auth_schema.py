from pydantic import BaseModel, EmailStr
from datetime import datetime

class SignUp(BaseModel):
    name: str
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}

class Login(BaseModel):
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}

class DoctorResponse(BaseModel):
    doctor_id: int
    name: str
    email: str
    password: str
    specialization: str | None = None
    date_join: datetime
    about: str | None = None
    phone_no: str | None = None

    model_config = {"from_attributes": True}

class DoctorUpdate(BaseModel):
    specialization: str
    about: str
    phone_no: str