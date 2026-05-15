import asyncio
import json
import hashlib
import logging
from logging.handlers import RotatingFileHandler

import httpx
from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session

from database import get_db, local_session
from rate_limiting import limiter
from schemas import config_schema as schema
import model

router = APIRouter(tags=['Config'])

logger = logging.getLogger("ehr_config")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

handler = RotatingFileHandler(r"logs/config.log", maxBytes=1000000, backupCount=2)
handler.setFormatter(formatter)
logger.addHandler(handler)

# in-memory cache — lives as long as the server is running
_cache = {
    "hash":    None,
    "records": None,
}


@router.post("/change-config-status", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def change_config_status(conf_data: schema.ChangeConfig, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Change the hold status of the current configuration.

    **Request Body:**
    - `hold_flag` (bool, required): Set to True to hold the configuration, False to release it.

    **Response (201 Created):**
    Returns a JSON message indicating the status change:
    ```json
    {
      "message": "Config status changed to: true"
    }
    ```
    Or if a new configuration was created:
    ```json
    {
      "message": "New configuration added"
    }
    ```

    **Request Schema (`schema.ChangeConfig`):**
    - `hold_flag` (bool)

    **Behavior:**
    - Queries the most recent unsent configuration (sent_to_engine == False)
    - If no unsent configuration exists, creates a new one with hold_flag set to True
    - Otherwise, updates the hold_flag on the existing configuration

    **Error Responses:**
    - `500 Internal Server Error`: Unexpected database or server error
    """
    try:
        config = db.query(model.Config).filter(model.Config.sent_to_engine == False) \
            .order_by(desc(model.Config.config_id)).first()
        if not config:
            config = model.Config(data=[], history={}, hold_flag=True, sent_to_engine=False)
            db.add(config)
            db.commit()
            return {"message": "New configuration added"}

        config.hold_flag = conf_data.hold_flag
        db.add(config)
        db.commit()
        logger.info(f"Config status changed to: {config.hold_flag}")
        return JSONResponse(content={"message": f"Config status changed to: {config.hold_flag}"})
    except Exception as e:
        logger.error(f"Error changing config status: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")

async def _post_config(config_id: int, data: str):
    try:
        timeout = httpx.Timeout(60.0, connect=5.0) # connect=5.0 means if we can't establish a connection within 5 seconds, give up immediately. The overall timeout for the request is 60 seconds.
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post("http://127.0.0.1:9000/batch", content=str(data))
            response.raise_for_status() # raises an exception if the response status code is 4xx or 5xx, which we can catch and log

        bg_db = local_session()
        try:
            config = bg_db.get(model.Config, config_id)
            if config:
                config.sent_to_engine = True
                bg_db.add(config)
                bg_db.commit()
                logger.info(f"Config with ID {config_id} successfully sent to engine")
        finally:
            bg_db.close()
    except httpx.TimeoutException:
        logger.error(f"Timed out while sending config with ID {config_id} to engine")
    except httpx.HTTPStatusError as exp:
        logger.error(
            f"Engine rejected config with ID {config_id}: "
            f"status={exp.response.status_code}, response={exp.response.text}"
        )
    except Exception as exp:
        logger.exception(f"Unexpected error while sending config with ID {config_id} to engine: {str(exp)}")

  
@router.post("/sent-config-to-engine")
@limiter.limit("20/minute")
def sent_config_to_engine(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Mark the current configuration as sent to the InterfaceEngine.

    **Response (200 OK):**
    Returns a JSON confirmation message:
    ```json
    {
      "message": "Config with ID 1 sent to engine"
    }
    ```
    Or if no unsent configuration exists:
    ```json
    {
      "message": "No unsent configuration found"
    }
    ```

    **Behavior:**
    - Queries the most recent unsent configuration (sent_to_engine == False)
    - Sets sent_to_engine flag to True, marking it as processed
    - Updates the configuration in the database
    - Logs the operation

    **Note:**
    - This endpoint prepares the configuration for transmission to the InterfaceEngine
    - The actual bulk data transmission logic should be implemented in this function

    **Error Responses:**
    - `500 Internal Server Error`: Unexpected database or server error
    """
    try:
        config = db.query(model.Config).filter(model.Config.sent_to_engine == False) \
            .order_by(desc(model.Config.config_id)).first()
        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No unsent configuration found")
        if config.data == []:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current configuration is empty, nothing to send")

        asyncio.create_task(_post_config(config.config_id, config.data)) # send batch to the engine.

        logger.info(f"Config with ID {config.config_id} queued to send to engine")
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"message": f"Config with ID {config.config_id} queued to send to engine"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending config to engine: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")
    
@router.get("/config-history", response_model=list[schema.ConfigHistory])
@limiter.limit("20/minute")
def config_history(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve the configuration history with operational statistics.

    **Response (200 OK):**
    Returns a JSON array of records showing lab-level operational counts:
    ```json
    [
        {
            "lab_name": "IDC",
            "submit-lab-result": 2,
        },
        {
            "lab_name": "CITI Lab",
            "submit-lab-result": 1
        }
    ]
    ```

    **Caching Behavior:**
    - Uses MD5 hash-based caching to avoid re-parsing large configuration data
    - Compares current config data hash with cached hash
    - Returns cached result if hash matches; re-parses and re-caches if data has changed
    - Cache persists for the lifetime of the server process

    **Query Process:**
    - Retrieves the most recent unsent configuration (sent_to_engine == False)
    - Calls parse_config() to transform the nested history structure into flat records
    - Each record represents a lab's operation count

    **Error Responses:**
    - `500 Internal Server Error`: Unexpected database or server error
    """
    try:
        config = db.query(model.Config).filter(model.Config.sent_to_engine == False) \
            .order_by(desc(model.Config.config_id)).first()
        
        # turn the JSON into a stable string and hash it
        raw = json.dumps(config.data, sort_keys=True)
        current_hash = hashlib.md5(raw.encode()).hexdigest()

        # if hash matches → return cached result, skip parsing
        if _cache["hash"] == current_hash:
            return _cache["records"]

        # hash changed (or first run) → parse and cache
        records = parse_config(config.history)  # your parsing logic here

        _cache["hash"]    = current_hash
        _cache["records"] = records

        return records
        
    except Exception as e:
        logger.error(f"Error retrieving config history: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")

def parse_config(data):
    try:
        records = []
        for hospital_name, operations in data.items():
            records.append({
                "hospital_name": hospital_name,
                "submit-lab-result": operations.get("submit-lab-result", 0)
            })
        return records
    except Exception as e:
        logger.error(f"Error parsing config history: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")
