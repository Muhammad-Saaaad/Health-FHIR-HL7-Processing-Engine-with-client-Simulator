from pydantic import BaseModel

class ClaimSubmission(BaseModel):
    vid: int
    mpi: int
    service_included: bool
    lab_included: bool
    total_fee: float