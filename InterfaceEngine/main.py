import json
import logging
import asyncio

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, status, HTTPException, Request

from api import server, route, endpoint
from database import engine, session_local
import models

logging.basicConfig(
    filename="message.log",
    level=logging.INFO,
    format= "%(asctime)s - %(levelname)s - %(message)s"
)

@asynccontextmanager # handle lifespan events like startup or shutdown
async def lifeSpan(app: FastAPI):
    app.state.route_manager_task = asyncio.create_task(route_manager())

    yield
    
    app.state.route_manager_task.cancel()
    return

app = FastAPI(title="Interface Engine", lifespan=lifeSpan)
models.Base.metadata.create_all(bind=engine)

app.include_router(server.router, prefix="/server")
app.include_router(route.router, prefix="/route")
app.include_router(endpoint.router, prefix="/endpoint")


@app.get("/")
def check_health():
    return {"message": "✔ Interface Engine running"}

active_listners = {}
route_queue = {}

async def route_manager():
    try:
        while True:
            db = session_local()
            routes = db.query(models.Route).all()
            db.close()

            for route in routes:
                if route.route_id not in active_listners:

                    route_queue[route.route_id] = asyncio.Queue()
                    task = asyncio.create_task(worker(route))
                    active_listners[route.route_id] = task
                    logging.info(f"worker start for route {route.route_id}")
            
            await asyncio.sleep(5)
    except Exception as exp:
        return str(exp)

async def worker(route):
    try:
        db = session_local()
        dest_endpoint= db.get(models.Endpoints, route.dest_endpoint_id)
        dest_server = db.get(models.Server, route.dest_server_id)
        db.close()

        dest_endpoint_url = f"http://{dest_server.ip}:{dest_server.port}{dest_endpoint.url}"

        while True:
            msg = await route_queue[route.route_id].get()
            print(msg)
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url=dest_endpoint_url, json=msg)
                    if response.status_code == 200 or response.status_code == 201:
                        logging.info("Sucessfully Send to url: {dest_endpoint_url}")
                    else:
                        logging.error("data was not send to url: {dest_endpoint_url}")
                
            except Exception as exp:
                logging.error(f"{exp} \nThis came when sending data to url: {dest_endpoint_url}")

    except Exception as exp:
        return str(exp)

@app.post("/{full_path:path}", status_code=status.HTTP_200_OK)
async def ingest(full_path: str, req: Request):
    try:
        print(full_path)
        payload = await req.json()

        db = session_local()
        # check url
        endpoint = db.query(models.Endpoints).filter(models.Endpoints.url == '/'+full_path).first()
        if not endpoint:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'The endpoint url: /{full_path} is not valid')
        
        routes = db.query(models.Route).filter(models.Route.src_endpoint_id == endpoint.endpoint_id).all()
        db.close()
        for route in routes:
            await route_queue[route.route_id].put(payload)
        
        return {"message": "sucessfully send data to all destinations"}

    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))


if "__main__" == __name__:
    import uvicorn
    uvicorn.run("main:app", port=9000, reload=True, host="0.0.0.0")
    
