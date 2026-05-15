from pydantic import BaseModel, EmailStr

class SystemUserCreate(BaseModel):
    user_name: str
    email: EmailStr
    password: str  
    insurance_id: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    insurance_id: str

class Admin(BaseModel):
    email: EmailStr
    password: str

class SystemUserDisplay(BaseModel):
    user_id: int
    insurance_id: str | None = None
    user_name: str
    email: EmailStr
    roll: int

    model_config = {"from_attributes": True}
