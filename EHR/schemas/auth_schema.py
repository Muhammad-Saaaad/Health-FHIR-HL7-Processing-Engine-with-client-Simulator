from pydantic import BaseModel, EmailStr

class SignUp(BaseModel):
    name: str
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}

class Login(BaseModel):
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}
