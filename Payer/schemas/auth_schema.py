from pydantic import BaseModel, EmailStr

class SystemUserCreate(BaseModel):
    user_name: str
    email: EmailStr
    password: str  

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SystemUserDisplay(BaseModel):
    user_id: int
    user_name: str
    email: EmailStr

    model_config = {"from_attributes": True}