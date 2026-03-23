from pydantic import BaseModel, Field, field_validator, ValidationError

class Server(BaseModel):
    server_id: int
    name: str
    protocol: str
    
    model_config= {"from_attributes": True}

class Endpoint(BaseModel):
    endpoint_id: int
    url: str

    model_config= {"from_attributes": True}

class GetRoute(BaseModel):

    route_id: int
    channel_name: str
    src_server: Server
    src_endpoint: Endpoint
    dest_server: Server
    dest_endpoint: Endpoint
    msg_type: str

    model_config= {"from_attributes": True}

class AddRoute(BaseModel):

    name: str = Field(..., min_length=1, description="Route Name cannot be empty")

    src_server_id: int = Field(..., gt=0) # means greater then 0
    src_endpoint_id: int = Field(..., gt=0)
    dest_server_id: int = Field(..., gt=0)
    dest_endpoint_id: int = Field(..., gt=0)

    msg_type: str = Field(..., min_length=1)

    rules : dict

    @field_validator('name', 'msg_type')
    @classmethod
    def check_not_empty(cls, value, info):
        if not value.strip():
            raise ValueError(f'{info.field_name} cannot be empty or whitespace only')
        return value.strip()
# rules includes -->
# src_paths: list[int]
# dest_paths: list[int]
# transform: str
# config: dict