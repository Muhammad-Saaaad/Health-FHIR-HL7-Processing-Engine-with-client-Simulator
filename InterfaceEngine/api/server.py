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
    """
    Register a new external server (EHR, LIS, Payer, etc.) in the Interface Engine.

    Before saving, the engine performs a live health check by hitting the server's `/health`
    endpoint. If the server is unreachable or returns a non-200 response, registration is rejected.

    **Request Body:**
    - `name` (str, required): Unique descriptive name for this server (e.g., "EHR-Server", "LIS-Lab").
    - `ip` (str, required): IP address or hostname of the server (e.g., "192.168.1.10" or "localhost").
    - `port` (int, required): Port number on which the server is running (e.g., 8001).
    - `protocol` (str, required): Messaging protocol this server uses — `"FHIR"` or `"HL7"`.

    **Response (201 Created):**
    Returns a confirmation message:
    - `message`: "Server added successfully"

    **Side Effects:**
    - Sets the server's initial `status` to `"Active"`.
    - A background health monitoring loop (`server_health`) runs every 60 seconds and
      automatically updates `status` to `"Active"` or `"Inactive"` based on reachability.

    **Constraints:**
    - Server name must be unique.
    - The server must be reachable and return HTTP 200 on `GET http://{ip}:{port}/health`.

    **Error Responses:**
    - `409 Conflict`: A server with this name already exists
    - `400 Bad Request`: Server is unreachable or health check failed
    - `400 Bad Request`: Unexpected database error
    """
    if db.query(models.Server).filter(models.Server.name == server.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Server with this name already exists")

    async with httpx.AsyncClient() as client:
        if not await server_health_check(client, server.ip, server.port):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Server is not reachable or unhealthy")

    try:
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
    """
    Retrieve all registered servers in the Interface Engine.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of all server records. Each item includes:
    - `server_id`: Unique server identifier
    - `name`: Server's descriptive name
    - `ip`: Server IP address or hostname
    - `port`: Server port number
    - `protocol`: Messaging protocol (`"FHIR"` or `"HL7"`)
    - `status`: Current health status (`"Active"` or `"Inactive"`)

    **Note:**
    - `status` is automatically updated every 60 seconds by the background health checker.
    - Returns an empty list if no servers are registered.

    **Error Responses:**
    - `400 Bad Request`: Unexpected database error
    """
    try:
        servers = db.query(models.Server).all()
        return servers
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")


@router.get("/specific-server/{server_id}", status_code=status.HTTP_200_OK, response_model=GetServer)
def specific_server(server_id: int, db: Session = Depends(get_db)):
    """
    Retrieve details of a specific server by its ID.

    **Path Parameters:**
    - `server_id` (int, required): The unique identifier of the server to retrieve.

    **Response (200 OK):**
    Returns the server record including:
    - `server_id`, `name`, `ip`, `port`, `protocol`, `status`

    **Error Responses:**
    - `404 Not Found`: No server exists with the given `server_id`
    """
    is_server = db.get(models.Server, server_id)
    if not is_server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Server id {server_id} not found")
        
    return is_server

@router.put("/update-server/{server_id}", status_code=status.HTTP_200_OK)
def update_server(server_id: int, server: AddUpdateServer, db: Session = Depends(get_db)):
    """
    Update the configuration of an existing registered server.

    **Path Parameters:**
    - `server_id` (int, required): The unique identifier of the server to update.

    **Request Body:**
    - `name` (str, required): New unique name for the server.
    - `ip` (str, required): Updated IP address or hostname.
    - `port` (int, required): Updated port number.
    - `protocol` (str, required): Updated messaging protocol (`"FHIR"` or `"HL7"`).

    **Response (200 OK):**
    Returns a confirmation message:
    - `message`: "Server updated successfully"

    **Constraints:**
    - The new `name` must not already be used by a different server.

    **Error Responses:**
    - `404 Not Found`: No server exists with the given `server_id`
    - `409 Conflict`: Another server already has the requested name
    - `400 Bad Request`: Unexpected database error
    """
    existing_server = db.query(models.Server).filter(models.Server.server_id == server_id).first()
    if not existing_server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    
    # if you want to implement or here you write a or_() in the filter and then the conditions
    if db.query(models.Server).filter(models.Server.server_id != server_id, models.Server.name == server.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Server with this name already exists")
        
    try:
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
    """
    Permanently delete a registered server from the Interface Engine.

    **Path Parameters:**
    - `server_id` (int, required): The unique identifier of the server to delete.

    **Response (200 OK):**
    Returns a confirmation message:
    - `message`: "Server deleted successfully"

    **Warning:**
    - Deleting a server may cascade and remove associated endpoints and routes depending
      on the database foreign key constraints configured in the schema.

    **Error Responses:**
    - `404 Not Found`: No server exists with the given `server_id`
    - `400 Bad Request`: Unexpected database error (e.g., FK constraint violation)
    """
    existing_server = db.query(models.Server).filter(models.Server.server_id == server_id).first()
    if not existing_server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
        
    try:
        db.delete(existing_server)
        db.commit()
        return {"message": "Server deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(e)}")

async def server_health():
    """
    Background coroutine that continuously monitors all registered servers' health status.

    Runs an infinite loop, sleeping 60 seconds between each check. On each iteration it:
    1. Queries all servers from the database.
    2. Hits `GET http://{ip}:{port}/health` for each server with a 5-second timeout.
    3. Updates each server's `status` to `"Active"` or `"Inactive"` if it changed.
    4. Commits the changes to the database.

    This function is intended to be launched as a background task on application startup
    (e.g., via `asyncio.create_task(server_health())`). It is not an HTTP endpoint.
    """
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


async def server_health_check(client, ip: str, port: int):
    """
    Perform a single health check against a server's `/health` endpoint.

    Sends `GET http://{ip}:{port}/health` with a 5-second timeout.

    Args:
        client (httpx.AsyncClient): A shared async HTTP client.
        ip (str): Server IP address or hostname.
        port (int): Server port number.

    Returns:
        bool: `True` if the server responds with HTTP 200, `False` for any error or non-200 response.
    """
    try:
        response = await client.get(f"http://{ip}:{port}/health", timeout=5)
        return response.status_code == 200
    except:
        return False
