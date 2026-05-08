import json
import hashlib
import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
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
            return {"message": "No unsent configuration found"}

        config.sent_to_engine = True
        db.add(config)
        db.commit()

        # add the logic here to sent the bulk data to engine.

        logger.info(f"Config with ID {config.config_id} sent to engine")
        return JSONResponse(content={"message": f"Config with ID {config.config_id} sent to engine"})
    except Exception as e:
        logger.error(f"Error sending config to engine: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")
    
@router.get("/config-history", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
def config_history(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve the configuration history with operational statistics.

    **Response (200 OK):**
    Returns a JSON array of records showing hospital-level operational counts:
    ```json
    [
      {
        "hospital": "Hospital A",
        "operation": "add-patient",
        "count": 10
      },
      {
        "hospital": "Hospital A",
        "operation": "add-visit",
        "count": 20
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
    - Each record represents a hospital's operation count

    **History Data Format:**
    Input history is expected in the format:
    ```
    {"Hospital A": {"add-patient": 10, "add-visit": 20}, "Hospital B": {"add-patient": 5, "submit-claim": 15}}
    ```

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
            for operation, count in operations.items():
                records.append({
                    "hospital": hospital_name,
                    "operation": operation,
                    "count": count
                })
        return records
    except Exception as e:
        logger.error(f"Error parsing config history: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")