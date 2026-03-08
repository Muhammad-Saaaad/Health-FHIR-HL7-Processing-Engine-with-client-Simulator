from pydantic import BaseModel
from datetime import date

class Patient(BaseModel):
    mpi: int
    nic: str
    name: str
    phone_no: str | None
    gender: str
    date_of_birth: date
    address: str | None

    model_config = {"from_attributes": True}