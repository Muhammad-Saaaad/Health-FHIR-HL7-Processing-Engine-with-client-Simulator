from datetime import datetime
from pydantic import BaseModel


class Vitals(BaseModel):
    type: str 
    nic:str
    systolic: str | None = None
    diastolic: str | None = None
    value: str | None = None    
    unit: str
    meal_time: str | None = None

class SendVitals(BaseModel):
    patient_nic : str
    doctor_id : int
