import os
import json
import logging
from queue import Queue

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, status, HTTPException, Request
from redis import Redis

from schema import Server

path = os.path.join(os.getcwd(), 'message.log')
logging.basicConfig(
    filename=path,
    level=logging.INFO,
    format= "%(asctime)s - %(levelname)s - %(message)s"
)

@asynccontextmanager # handle lifespan events like startup or shutdown
async def lifeSpan(app: FastAPI):
    app.state.server_path = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\servers.json"
    app.state.destination_path = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\destinations.json"

    app.state.redis = Redis(host='localhost', port="6379")
    app.state.http_client = httpx.AsyncClient() # call api endpoints
    app.state.channel_queue = Queue()
    yield

    # app.state.redis.shutdown()
    return

app = FastAPI(title="Interface Engine", lifespan=lifeSpan)



@app.get("/")
def check_health():
    return {"message": "✔ Interface Engine running"}

@app.get("/all-servers", status_code=status.HTTP_200_OK, response_model=list[Server])
def all_servers(req: Request):
    
    if not os.path.exists(req.app.state.server_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file path not valid")
    
    with open(req.app.state.server_path, "r") as f:
        servers = json.load(f)
    
    return servers
    
@app.post("/add-server", status_code=status.HTTP_201_CREATED)
def add_server(req: Request, server: Server):

    if not os.path.exists(req.app.state.server_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file path not valid")
    
    if not server.ip or not server.port or not server.db_connection_str or not server.server_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enter all the data")

    with open(req.app.state.server_path, "r") as f:
        servers = json.load(f)
    
    with open(req.app.state.destination_path, "r") as f:
        destinations = json.load(f)

    for s in servers:
        if s['port'] == server.port:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="port already exists")
        elif s['db_connection_str'] == server.db_connection_str:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="db connection String already exists")
        elif s['server_name'] == server.server_name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="server name already exists")
    
    servers.append({
        "ip": server.ip,
        "port": server.port,
        "db_connection_str" : server.db_connection_str,
        "server_name": server.server_name
    })

    with open(req.app.state.server_path, "w") as f:
        json.dump(servers, f, indent=4)
    
    destinations.append({
        server.server_name: f"http://{server.ip}:{server.port}/hl7/push"
    })

    with open(req.app.state.destination_path, "w") as f:
        json.dump(destinations, f, indent=4)
    
    return {"message": "server added sucessfully"}
        

@app.get("/get_data_from")
async def data_from(req: Request):

    value = req.app.state.redis.get("entries")

    if value is None:
        response = await req.app.state.http_client.get("http://127.0.0.1:8001/patients")
        value = response.json()
        data_str = json.dumps(value)
        req.app.state.redis.set("entries", data_str)
        
    return json.loads(value)

@app.post("/fhir/push")
async def recieve_fhir_message(req : Request):
    fhir_payload = await req.json()
    print(fhir_payload)

    logging.info("Data recieved")

    response = httpx.post("http://127.0.0.1:8002/hl7/push", json=fhir_payload)
    if response.status_code == 200:
        logging.info("Data sent to lab")

    return {"message": "recieve"}

if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", port=9000, reload=True)
    
