from pydantic import BaseModel, Json
from typing import Literal, Dict, Any

class AddEndpoint(BaseModel):

    server_id: int
    server_protocol: Literal["FHIR", "HL7"]
    url: str
    sample_msg: Dict[str, Any] | str # Changed from Json to Dict for easier handling