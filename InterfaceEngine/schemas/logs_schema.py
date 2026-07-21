from datetime import datetime
from typing import Optional
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
    src_message: str | None
    dest_message: str | None

    model_config = {"from_attributes": True}

class LogResponse(BaseModel):
    log_id: int
    datetime: datetime
    status: str
    operation_heading: str
    operation_message: Optional[str] = None
    src_message: Optional[str] = None
    dest_message: Optional[str] = None
    dest_system_name: Optional[str] = None
    src_systemid: Optional[str] = None

    class Config:
        from_attributes = True
