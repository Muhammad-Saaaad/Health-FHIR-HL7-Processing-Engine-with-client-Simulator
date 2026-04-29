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
    """Doctor object response schema for all endpoints returning doctor data."""
    doctor_id: int
    name: str
    email: str
    password: str
    specialization: str = None
    date_join: datetime
    about: str = None
    phone_no: str = None

    model_config = {"from_attributes": True}
