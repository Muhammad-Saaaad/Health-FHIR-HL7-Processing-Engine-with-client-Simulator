from datetime import date
from pydantic import BaseModel

class get_patient(BaseModel):
    mpi : int
    nic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: date | None
    address : str | None

    model_config = {"from_attributes": True}

class post_patient(BaseModel):
    nic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: date | None
    address : str | None

    model_config = {"from_attributes": True}