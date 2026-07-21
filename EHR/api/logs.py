from fastapi import APIRouter, HTTPException
import httpx
from typing import List

router = APIRouter(tags=["Logs"])

ENGINE_API_URL = "http://localhost:9000/logs/engine/logs"

@router.get("/v1/logs")
async def get_filtered_logs_from_ehr_lis(system_id: str):
    """
    Front-end se system_id aayegi. Yeh API Engine se saara data legi 
    aur yahan EHR/LIS side par filter kar ke return karegi.
    """
    async with httpx.AsyncClient() as client:
        try:
            # 1. Engine se saara data mangwaya
            response = await client.get(ENGINE_API_URL)
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="Engine API se data nahi mila")
                
            all_logs = response.json()
            
            # 2. Filter lagaya front-end se aane wali system_id ki base par
            filtered_logs = [
                log for log in all_logs 
                if log.get("src_systemid") == system_id 
            ]
            
            return filtered_logs
            
        except httpx.RequestError as exc:
            raise HTTPException(status_code=500, detail=f"Engine se raabta nahi ho saka: {exc}")