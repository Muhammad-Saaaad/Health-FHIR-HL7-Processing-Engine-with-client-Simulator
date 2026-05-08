from pydantic import BaseModel

class ChangeConfig(BaseModel):
    hold_flag: bool    