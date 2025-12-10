from datetime import datetime
from pydantic import BaseModel


class get_patient(BaseModel):
    patient_id : int
    cnic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: datetime | None
    address : str | None

    model_config = {"from_attributes": True}

class post_patient(BaseModel):
    cnic : str
    name : str
    phone_no : str | None
    gender : str
    date_of_birth: datetime | None
    address : str | None

    model_config = {"from_attributes": True}

class VisitNote(BaseModel):
    patient_id : int
    doctor_id : int
    bill_id : int | None

    visit_date : datetime
    note_title : str
    patient_complaint : str
    dignosis : str
    note_details : str