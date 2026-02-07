from pydantic import BaseModel

class GetRoute(BaseModel):

    route_id: int
    name: str
    src_endpoint_id: int
    dest_endpoint_id: int
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