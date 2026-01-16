from pydantic import BaseModel, Field, AliasPath
from datetime import datetime

class PatientClaimCreate(BaseModel):
    policy_id: int
    patient_id: int
    service_name: str
    bill_amount: float
    provider_phone_no: str | None =  None

class AllClaims(BaseModel):
    claim_id: int
    name: str
    service_name: str
    phone_no: str | None
    created_at: datetime | None

class ClaimsPerPatient(BaseModel):
    patient_id: int
    all_claims: list[AllClaims]

    model_config = {"from_attributes": True}

class PatientClaimDisplay(BaseModel):
    claim_id: int

    policy_id: int
    patient_id: int

    # Field is use to provide extra configurations for a object
    # vaidation_alias is use to take a object and maps it to the key
    # AliasPath take the objects from a specific path define when the object is in a relationship

    patient_name: str = Field(validation_alias=AliasPath("patient", "name"))
    cnic: str = Field(validation_alias=AliasPath("patient", "cnic"))
    provider_phone_no: str
    patient_phone_no: str = Field(validation_alias=AliasPath("patient", "phone_no"))
    service_name: str
    bill_amount: float
    claim_status: str

    # this helps when you return data take from database object
    # it not only validate the data but also make sure that the data is converted into
    # json and then it send the data to the user
    # works when you set response_model=schema.class_name
    model_config = {"from_attributes": True}