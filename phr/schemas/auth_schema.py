from pydantic import BaseModel

class SignUp(BaseModel):
    nic: str
    password: str

    model_config = {"from_attributes": True}

class Login(BaseModel):
    nic: str
    password: str

    model_config = {"from_attributes": True}
