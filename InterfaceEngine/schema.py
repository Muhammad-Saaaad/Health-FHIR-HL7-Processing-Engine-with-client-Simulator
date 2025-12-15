from pydantic import BaseModel

class Server(BaseModel):
    ip: str
    port: int
    db_connection_str : str
    server_name: str
