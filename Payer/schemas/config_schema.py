from pydantic import BaseModel

class ChangeConfig(BaseModel):
    hold_flag: bool    

class ConfigHistory(BaseModel):
    hospital_name: str

    add_patient_count: int
    add_visit_count: int
    add_claim_count: int