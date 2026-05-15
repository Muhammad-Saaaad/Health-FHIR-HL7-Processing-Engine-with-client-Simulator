from pydantic import BaseModel, Field, AliasPath, field_serializer
from datetime import datetime

class PatientClaimCreate(BaseModel):
    policy_id: int
    patient_id: int
    service_name: str
    bill_amount: float
    provider_phone_no: str | None =  None

class AllClaims(BaseModel):
    claim_id: int
    nic: str | None
    policy_number: int
    name: str
    created_at: datetime | None
    status: str = "Pending" # Default value for claim status

    @field_serializer("created_at")
    def serialize_created_at(value: datetime | None) -> datetime | None:
        if value is not None:
            return value.strftime("%B %d, %Y")
        return value
class ClaimsPerPatient(BaseModel):
    patient_id: int
    all_claims: list[AllClaims]

    model_config = {"from_attributes": True}

class PatientClaimDisplay(BaseModel):
    claim_id: int

    policy_id: int
    pid: int

    # Field is use to provide extra configurations for a object
    # vaidation_alias is use to take a object and maps it to the key
    # AliasPath take the objects from a specific path define when the object is in a relationship

    patient_name: str = Field(validation_alias=AliasPath("patient", "name"))
    patient_phone_no: str | None = Field(validation_alias=AliasPath("patient", "phone_no"))
    gender: str = Field(validation_alias=AliasPath("patient", "gender"))

    bill_amount : float
    total_coverage: float = Field(validation_alias=AliasPath("policy", "total_coverage"))
    amount_used: float = Field(validation_alias=AliasPath("policy", "amount_used"))
    service_included: bool
    tests_included: bool   

    # this helps when you return data take from database object
    # it not only validate the data but also make sure that the data is converted into
    # json and then it send the data to the user
    # works when you set response_model=schema.class_name
    model_config = {"from_attributes": True}
    
class ExpenseBreakdown(BaseModel):
    claim_date: datetime | str
    service_included: bool
    tests_included: bool
    total_amount: float
    status: str

    @field_serializer("claim_date")
    def serialize_claim_date(value: datetime ) -> str:
        return value.strftime("%B %d, %Y")
