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

path = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\message.log"
logging.basicConfig(
    filename=path,
    level=logging.INFO,
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
        server.server_name: f"http://{server.ip}:{server.port}/push"
    })

    with open(req.app.state.destination_path, "w") as f:
        json.dump(destinations, f, indent=4)
    
    return {"message": "server added sucessfully"}

@app.post("/fhir/push", status_code=status.HTTP_200_OK)
async def recieve_fhir_message(req : Request):
    """
        Recieve data from any Health Care System, and send it to other systems.
    """
    try:

        fhir_payload = await req.json()
        logging.info(f"Data recieved: payload {fhir_payload}")
        if fhir_payload['source'] == "ehr":
            global Ehr_channel_queue
            Ehr_channel_queue.put(fhir_payload)
        
        elif fhir_payload['source'] == 'LIS': 
            global Lis_channel_queue
            Lis_channel_queue.put(fhir_payload)

        elif fhir_payload['source'] == 'Payer': 
            global Payer_channel_queue
            Payer_channel_queue.put(fhir_payload)
        
        endpoints = []

        with open(req.app.state.destination_path, 'r') as f:
            destination_urls = json.load(f)
            for url in destination_urls:
                for destination in fhir_payload['destination']:
                    
                    if destination in url:
                        endpoints.append({destination: url[destination]})
        
        for endpoint in endpoints:
            destination = list(endpoint.keys())[0]
            endpoint = list(endpoint.values())[0]
            response = await send_payload(payload=fhir_payload, destination=destination ,endpoint=endpoint)
            if response.status_code == 200:
                logging.info(response)
                
            else:
                logging.error(response)
                raise HTTPException({"message", response.content}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return {"message": "Sucessfull"}
    except Exception as exp:
        logging.error(f"Error occured: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error {str(exp)}")

async def send_payload(payload: dict, destination: str, endpoint: dict):
    try:
        async with httpx.AsyncClient() as client:
            endpoint = endpoint+"/register/patient/"
            response = await client.post(endpoint, json=payload)
            logging.info(f"Response Recieved {response} \nfrom "+destination)
            return response
    except Exception as exp:
        return str(exp)


@app.post("/test/request")
async def send_test_message(req: Request):
    try:
        global Ehr_channel_queue

        data = {"patient_id": 2, "doctor_id": 2,}
        response = await req.app.state.http_client.post("http://127.0.0.1:9000/fhir/push", json=data)

        if response.status_code == 200:
            return {"message": "successfull"}
            # return {"message": "successfull", "data": Ehr_channel_queue.get()}
        else:
            return {"message": "unsuccessfull"}
    except Exception as exp:
        logging.error(f"Error occured: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

def channel_worker(channel, channel_name):

    """_summary_
        Here the Channel stays open, and a single channel is then use to route 1 system to multiple different systems.
    """
    # global Ehr_channel_queue
    while True:
        with open(r'E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\destinations.json', 'r') as f:
            destination_urls = json.load(f)

        messgae = channel.get() # sleeps, only wake up when there is a data

        destination = messgae.get("destination") # send message to 1 system
        
        for des in destination_urls:
            if destination in des.keys():
                url = des[destination]

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
# threading.Thread(
#     target=channel_worker,
#     args=(Ehr_channel_queue, "EHR_Channel"),
#     daemon=True
# ).start()
# threading.Thread(
#     target=channel_worker,
#     args=(Payer_channel_queue, "Payer_Channel"),
#     daemon=True
# ).start()
# threading.Thread(
#     target=channel_worker,
#     args=(Lis_channel_queue, "LIS_Channel"),
#     daemon=True
# ).start()


if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", port=9000, reload=True)
    
