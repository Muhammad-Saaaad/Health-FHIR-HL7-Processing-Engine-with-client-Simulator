from pydantic import BaseModel
from typing import Literal

class AddUpdateServer(BaseModel):

    name: str
    ip: str
    port: int
    protocol: Literal["FHIR", "HL7"]

class GetServer(BaseModel):
    
    server_id: int
    name: str
    ip: str
    port: int
    protocol: str
    status: str

    model_config = {"from_attributes": True}