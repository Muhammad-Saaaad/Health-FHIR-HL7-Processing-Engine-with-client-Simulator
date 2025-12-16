from pydantic import BaseModel, EmailStr, Field, AliasPath
from datetime import datetime, date

class SystemUserCreate(BaseModel):
    user_name: str
    email: EmailStr
    password: str  

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SystemUserDisplay(BaseModel):
    user_id: int
    user_name: str
    email: EmailStr

    model_config = {"from_attributes": True}

class PatientCreate(BaseModel):
    name: str
    cnic: str
    phone_no: str | None
    gender: str | None
    date_of_birth: date | None
    user_id: int | None

class PatientDisplay(BaseModel):
    p_id: int
    name: str
    cnic: str
    date_of_birth: date | None
    user_id: int | None

    model_config = {"from_attributes": True}

class patient_policy(BaseModel):
    policy_id: int
    category_name: str
    total_coverage: float
    amount_used : float
    description: str | None

class PatientPolicyDetails(BaseModel):
    p_id: int
    name: str
    cnic: str
    date_of_birth: date | None

    patient_policy : list[patient_policy]

class PolicyCreate(BaseModel):
    p_id: int
    u_id: int
    category_name: str
    total_coverage: float
    amount_used: float = 0.0
    description: str | None
    status: str


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