from pydantic import BaseModel, EmailStr

class SignUp(BaseModel):
    user_name: str
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}

class Login(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    user_id: int
    user_name: str
    email: EmailStr

    model_config = {"from_attributes": True}