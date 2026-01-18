from pydantic import BaseModel, Field
from datetime import datetime, date

class PatientBase(BaseModel):
    cnic: str = Field(..., max_length=20)
    fname: str = Field(..., max_length=25)
    lname: str | None
    dob: datetime | None
    gender: str = Field(..., max_length=10)
    phone: str | None
    dignosis: str | None

# --- Schema for Patient Creation ---
class Patient(BaseModel):
    mpi : int
    fname : str
    lname : str | None
    dob : datetime | date | None
    gender : str

    model_config = {"from_attributes": True}
