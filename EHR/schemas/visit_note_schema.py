from datetime import datetime
from pydantic import BaseModel, field_serializer

from .lab_schema import LoincMaster

class VisitNote(BaseModel):
    mpi : int
    doctor_id : int

    note_title : str
    patient_complaint : str
    dignosis : str
    note_details : str
    bill_amount : float

    lab_name: str | None
    test_names: list[LoincMaster] | None

    model_config = {"from_attributes": True}

class ViewBaseNote(BaseModel):
    note_id : int
    mpi : int
    doctor_id : int

    visit_date : datetime | str
    note_title : str | None

    @field_serializer("visit_date")
    def serialize_visit_date(self, value: datetime) -> str:
        return datetime.strftime(value, "%Y-%m-%d %H:%M:%S %p")
    
    model_config = {"from_attributes": True}

class ViewNote(BaseModel):
    note_id : int

    mpi : int
    doctor_id : int
    bill_id : int | None

    note_title : str | None
    patient_complaint : str | None
    dignosis : str | None
    note_details : str | None
    
    model_config = {"from_attributes": True}