from datetime import datetime
from pydantic import BaseModel

class LogEntry(BaseModel):
    log_id: int
    datetime: datetime
    status: str
    operation_message: str
    operation_heading: str

    model_config = {"from_attributes": True}

class LogMsg(BaseModel):
    log_id: int
    datetime: datetime
    status: str
    operation_heading: str
    src_message: str | dict | None
    dest_message: str | dict | None

    model_config = {"from_attributes": True}