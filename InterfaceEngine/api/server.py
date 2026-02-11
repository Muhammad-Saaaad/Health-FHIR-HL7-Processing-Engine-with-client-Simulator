import asyncio

import httpx
from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from schemas.server import AddUpdateServer, GetServer
import models
from database import get_db, session_local

router = APIRouter(tags=["Server"])

@router.post("/add-server", status_code=status.HTTP_201_CREATED)
async def add_server(server: AddUpdateServer, db: Session = Depends(get_db)):
    try:

        if db.query(models.Server).filter(models.Server.name == server.name).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Server with this name already exists")

        async with httpx.AsyncClient() as client:
            if not await server_health_check(client, server.ip, server.port):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Server is not reachable or unhealthy")

        new_server = models.Server(
            name=server.name,
            ip=server.ip,
            port=server.port,
            protocol=server.protocol,
            status ="Active"
        )
        db.add(new_server)
        db.commit()
        db.refresh(new_server)
        return {"message": "Server added successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.get("/all-servers", status_code=status.HTTP_200_OK, response_model=list[GetServer])
def all_servers(db: Session = Depends(get_db)):
    try:
        servers = db.query(models.Server).all()
        return servers
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")


@router.get("/specific-server/{server_id}", status_code=status.HTTP_200_OK, response_model=GetServer)
def specific_server(server_id: int, db: Session = Depends(get_db)):
    try:
        is_server = db.get(models.Server, server_id)
        if not is_server:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Server id {server_id} not found")
            
        return is_server
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")


@router.put("/update-server/{server_id}", status_code=status.HTTP_200_OK)
def update_server(server_id: int, server: AddUpdateServer, db: Session = Depends(get_db)):
    try:
        existing_server = db.query(models.Server).filter(models.Server.server_id == server_id).first()
        if not existing_server:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
        
        # if you want to implement or here you write a or_() in the filter and then the conditions
        if db.query(models.Server).filter(models.Server.server_id != server_id, models.Server.name == server.name).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Server with this name already exists")
        
        existing_server.name = server.name
        existing_server.ip = server.ip
        existing_server.port = server.port
        existing_server.protocol = server.protocol
        db.commit()
        return {"message": "Server updated successfully"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

@router.delete("/delete-server/{server_id}", status_code=status.HTTP_200_OK)
def delete_server(server_id: int, db: Session = Depends(get_db)):
    try:
        existing_server = db.query(models.Server).filter(models.Server.server_id == server_id).first()
        if not existing_server:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
        
        db.delete(existing_server)
        db.commit()
        return {"message": "Server deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

async def server_health():
    print("start status checking")
    while True: # after every 30 second we check all the servers status, if they are active or not
        try:
                db = session_local()
                servers = db.query(models.Server).all()

                async with httpx.AsyncClient() as client:
                    for server in servers:
                        is_alive= await server_health_check(client, server.ip, server.port)
                        new_status = 'Active' if is_alive else 'Inactive'
                        if server.status != new_status:
                            server.status = new_status
                
                db.commit()
        except Exception as exp:
            if db:
                db.rollback()
            print(f"Exception Error while checking status: {str(exp)}")
        finally:
            if db:
                db.close()
        await asyncio.sleep(60) # check status after every 30 seconds


async def server_health_check(client, ip: str, port: int): # checks the server health after every 60 seonds
    try:
        response = await client.get(f"http://{ip}:{port}/health", timeout=5)
        return response.status_code == 200
    except:
        return False
