from fastapi import APIRouter, status, HTTPException, Depends, Response, Request
from sqlalchemy.orm import Session

from schemas.logs_schema import LogEntry, LogMsg
import models
from database import get_db

router = APIRouter(tags=["Logs"])

@router.get("/show-logs", status_code=status.HTTP_200_OK, response_model=list[LogEntry])
async def show_logs(db: Session = Depends(get_db)):
    """
    Retrieve all logs from the database.

    **Response (200 OK):**
    Returns a list of log entries, where each entry contains:
    - `log_id` (int): Unique identifier for the log entry
    - `datetime` (datetime): Timestamp of the log entry
    - `Status` (str): (e.g., "Success", "Fail")
    - `level` (str): Level of the log entry (e.g., "INFO", "ERROR")
    - `operation_heading` (str): Heading or title of the operation
    - `operation_message` (str): Detailed message about the operation

    **Error Responses:**
    - 409 Conflict: Database retrieval error
    """
    try:
        logs = db.query(models.Logs).order_by(models.Logs.datetime.desc()).limit(20).all()
        return logs
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("/show-log-msg/{log_id}", status_code=status.HTTP_200_OK, response_model=LogMsg)
async def show_log_msg(log_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a specific log message from the database.

    **Response (200 OK):**
    Returns a list of log messages, where each message contains:
    - `datetime` (datetime): Timestamp of the log entry
    - `level` (str): Level of the log entry (e.g., "INFO", "ERROR")
    - `operation_heading` (str): Heading or title of the operation
    - `src_message` (str | None): Original message before processing
    - `dest_message` (str | None): Final message after processing

    **Error Responses:**
    - 409 Conflict: Database retrieval error
    """
    try:
        log = db.query(models.Logs).filter(models.Logs.log_id == log_id).first()
        return log
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))