import json
import logging
from queue import Queue
import threading

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, status, HTTPException, Request

from api import server, route, endpoint
from database import engine
import models

logging.basicConfig(
    filename="message.log",
    level=logging.INFO,
    format= "%(asctime)s - %(levelname)s - %(message)s"
)
Ehr_channel_queue = Queue()
Lis_channel_queue = Queue()
Payer_channel_queue = Queue()

@asynccontextmanager # handle lifespan events like startup or shutdown
async def lifeSpan(app: FastAPI):
    app.state.destination_path = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\InterfaceEngine\destinations.json"

    app.state.http_client = httpx.AsyncClient() # call api endpoints
    yield
    return

app = FastAPI(title="Interface Engine", lifespan=lifeSpan)
models.Base.metadata.create_all(bind=engine)

app.include_router(server.router, prefix="/server")
app.include_router(route.router, prefix="/route")
app.include_router(endpoint.router, prefix="/endpoint")


@app.get("/")
def check_health():
    return {"message": "✔ Interface Engine running"}

@app.post("/fhir/push", status_code=status.HTTP_200_OK)
async def recieve_fhir_message(req : Request):
    """
        Recieve data from any Health Care System, and send it to other systems.
    """
    try:

        payload = await req.json()
        logging.info(f"Data recieved: payload {payload}")
        if payload['source'] == "ehr":
            global Ehr_channel_queue
            Ehr_channel_queue.put(payload)
        
        elif payload['source'] == 'LIS': 
            global Lis_channel_queue
            Lis_channel_queue.put(payload)

        elif payload['source'] == 'Payer': 
            global Payer_channel_queue
            Payer_channel_queue.put(payload)
        
        endpoints = []


        # this will be use in routing.
        with open(req.app.state.destination_path, 'r') as f:
            destination_urls = json.load(f)
            for json_url in destination_urls:
                # [LIS, Payer]
                for destination in payload['destination']:
                    
                    if destination in json_url:
                        # endpoints.append({destination: json_url[destination]})
                        endpoints.append(json_url)
                        break
        
        for endpoint in endpoints:
            destination = list(endpoint.keys())[0]
            endpoint = list(endpoint.values())[0]
            response = await send_payload(payload=payload, destination=destination ,endpoint=endpoint)
            if response.status_code == 200:
                logging.info(response)
                
            else:
                logging.error(response)
                raise HTTPException({"message", response.content}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return {"message": "Sucessfull"}
    except Exception as exp:
        logging.error(f"Error occured: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error {str(exp)}")

async def send_payload(payload: dict, destination: str, endpoint: str):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(endpoint+"/register/patient/", json=payload)
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
    uvicorn.run("main:app", port=9000, reload=True, host="0.0.0.0")
    
