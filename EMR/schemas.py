from pydantic import BaseModel, EmailStr

class fetchDoctors(BaseModel):
    doctor_id : int
    name: str
    email: EmailStr
    password: str
    specialization: str
    phone_no: str
    date_join: str
    about: str

    model_config = {"from_attributes": True}