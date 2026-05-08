from pydantic import BaseModel, field_validator
from typing import Literal

class AddUpdateServer(BaseModel):

    system_id: str
    name: str
    ip: str
    port: int
    protocol: Literal["FHIR", "HL7"]
    category: Literal["EHR", "PHR", "LIS", "Payer"]

    @field_validator("name", "ip", mode="before")
    @classmethod
    def strip_required_strings(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

class GetServer(BaseModel):
    
    server_id: int
    system_id: str
    name: str
    ip: str
    port: int
    protocol: str
    category: str | None
    status: str

    model_config = {"from_attributes": True}