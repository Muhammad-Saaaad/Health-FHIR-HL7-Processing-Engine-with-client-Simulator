import os
import json
import logging
from queue import Queue
import threading

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, status, HTTPException, Request
# from redis import Redis

from schema import Server

path = os.path.join(os.getcwd(), 'message.log')
logging.basicConfig(
    filename=path,
    level=logging.DEBUG,
    format= "%(asctime)s - %(levelname)s - %(message)s"
)
Ehr_channel_queue = Queue()
Lis_channel_queue = Queue()
Payer_channel_queue = Queue()

@asynccontextmanager # handle lifespan events like startup or shutdown
async def lifeSpan(app: FastAPI):
    app.state.server_path = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\servers.json"
    app.state.destination_path = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\destinations.json"

    # app.state.redis = Redis(host='localhost', port="6379")
    app.state.http_client = httpx.AsyncClient() # call api endpoints
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
        

# @app.get("/get_data_from")
# async def data_from(req: Request):

#     value = req.app.state.redis.get("entries")

#     if value is None:
#         response = await req.app.state.http_client.get("http://127.0.0.1:8001/patients")
#         value = response.json()
#         data_str = json.dumps(value)
#         req.app.state.redis.set("entries", data_str)
        
#     return json.loads(value)

@app.post("/fhir/ehr/push")
async def recieve_fhir_message(req : Request):
    fhir_payload = await req.json()
    logging.info(f"Data recieved: payload {fhir_payload}")
    Ehr_channel_queue.put(fhir_payload)

    return {"message": "EHR Message queued"}

@app.post("/fhir/lis/push")
async def recieve_fhir_message(req : Request):
    fhir_payload = await req.json()
    logging.info(f"Data recieved: payload {fhir_payload}")
    Lis_channel_queue.put(fhir_payload)

    return {"message": "EHR Message queued"}

@app.post("/fhir/payer/push")
async def recieve_fhir_message(req : Request):
    fhir_payload = await req.json()
    logging.info(f"Data recieved: payload {fhir_payload}")
    Payer_channel_queue.put(fhir_payload)

    return {"message": "EHR Message queued"}

def channel_worker(channel, channel_name):

    """_summary_
        Here the Channel stays open, and a single channel is then use to route 1 system to multiple different systems.
    """
    while True:
        with open(r'E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\destinations.json', 'r') as f:
            destination_urls = json.load(f)

        messgae = channel.get() # sleeps, only wake up when there is a data

        destination = messgae.get("destination") # send message to 1 system
        
        for des in destination_urls:
            if destination in des.keys():
                url = des[destination]
        logging.debug(f"url = {url}")

        if not url:
            logging.error(f"The destination {destination} for channel {channel_name} was not found")
            channel.task_done()
            continue
        
        # here you will convert FHIR to hl7 and then convert hl7 to the reciever hl7 formate
        response = httpx.post(url=url, json=messgae)

        if response.status_code == 200:
            logging.info(f"data sent to destination {destination}")
        else:
            logging.info(f"failed to sent data to destination {destination}")
        
        Ehr_channel_queue.task_done()

# Daemon =Ture means the thread will run in the background
# this is how iguana behaves
threading.Thread(
    target=channel_worker,
    args=(Ehr_channel_queue, "EHR_Channel"),
    daemon=True
).start()
threading.Thread(
    target=channel_worker,
    args=(Payer_channel_queue, "Payer_Channel"),
    daemon=True
).start()
threading.Thread(
    target=channel_worker,
    args=(Lis_channel_queue, "LIS_Channel"),
    daemon=True
).start()


if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", port=9000, reload=True)
    
