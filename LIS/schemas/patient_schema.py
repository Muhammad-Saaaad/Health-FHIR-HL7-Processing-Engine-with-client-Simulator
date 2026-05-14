from datetime import datetime

from pydantic import BaseModel, field_serializer

from .lab_schema import LabBase

class PatientBase(BaseModel):
    nic: str
    fname: str 
    lname: str
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return value.strftime("%B %d, %Y")

    model_config = {"from_attributes": True}

class PatientDetail(BaseModel):
    nic: str
    fname: str
    lname: str
    gender: str
    age: datetime | str | None

    lab_reports : list[LabBase] = []

    @field_serializer("age")
    def serialize_age(self, value: datetime) -> str:
        today = datetime.today().date()
        # here first we calculate the year, then we check the month and day like this (5, 20) < (6, 15)
        # python will first compare the month, if its true or false, then return 1 or 0, if it is the same,
        # then python will compare the day and return 1 or 0, then we subtract that from the year to get the correct age.

        age_years = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        return f"{age_years} years"

    model_config = {"from_attributes": True}

class WaitingPatientList(BaseModel):
    test_req_id: int
    vid: str | None
    nic: str
    fname: str
    lname: str
    status: str
    date: datetime

    @field_serializer("date")
    def serialize_date(self, value: datetime) -> str:
        return value.strftime("%B %d, %Y")

class AcceptedPatientList(BaseModel):
    test_req_id: int
    test_name: str
    vid: str | None
    nic: str
    fname: str
    lname: str
    status: str
    date: datetime

    @field_serializer("date")
    def serialize_date(self, value: datetime) -> str:
        return value.strftime("%B %d, %Y")
