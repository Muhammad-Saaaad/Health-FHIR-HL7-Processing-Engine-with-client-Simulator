from pydantic import BaseModel, BeforeValidator
from datetime import datetime, date
from typing import Annotated

datestr = Annotated[str, BeforeValidator(lambda v: str(v.date()) )] # take the datetime and give only date.

class GetPatient(BaseModel):
    mpi: int 
    fname: str 
    lname: str | None
    dob: datetime | None
    gender: str 
    updated_at: datestr

    model_config = {"from_attributes": True}

# --- Schema for Patient Creation ---
class Patient(BaseModel):
    mpi : int
    fname : str
    lname : str | None
    dob : datetime | date | None
    gender : str

    model_config = {"from_attributes": True}
