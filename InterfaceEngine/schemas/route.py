from pydantic import BaseModel

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

    name: str

    src_server_id: int
    src_endpoint_id: int
    des_server_id: int
    des_endpoint_id: int

    msg_type: str

    rules : dict

# rules includes -->
# src_paths: list[int]
# dest_paths: list[int]
# transform: str
# config: dict