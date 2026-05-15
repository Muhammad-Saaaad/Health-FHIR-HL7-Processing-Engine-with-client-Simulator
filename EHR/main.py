import os
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SAWarning
import warnings
 
from database import engine, session_local
import model
from api import (
    authentication, 
    lab, 
    patient, 
    visit_note,
    claim,
    engine_service,
    config
)
from rate_limiting import limiter, rate_limit_exceeded_handler

warnings.filterwarnings("ignore", category=SAWarning)
os.makedirs(r"logs", exist_ok=True)

app = FastAPI(title="EHR System")
app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],
    allow_credentials= False,
    allow_headers=["*"],
    allow_methods=["*"]
)
model.Base.metadata.create_all(bind=engine) # once you run the server, then you should comment this, so this won't do issue with testing.

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(authentication.router)
app.include_router(lab.router)
app.include_router(patient.router)
app.include_router(visit_note.router)
app.include_router(claim.router)
app.include_router(engine_service.router)
app.include_router(config.router)

@app.get("/health/{system_id}")
def check_health(system_id: str):
    """
    Health-check endpoint for EHR service.

    **Response (200 OK):**
    - JSON object: `{ "message": "✔ EHR running" }`
    """
    db = session_local()
    try:
        server = db.query(model.Hospital).filter(model.Hospital.hospital_id == system_id).first()
        if not server:
            raise HTTPException(status_code=404, detail={"message": f"Server with system_id '{system_id}' not found."})
        return {"message": f"✔ EHR running for system_id '{system_id}'"}
    finally:
        db.close()

@app.post("/connected-labs-insuraces")  
async def get_connected_labs_insurances(request: Request):
    """
        take the connected system and give it to this variable that is 
        located in the labs_payers.py file.
    """
    data = await request.json()
    with open(r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\EHR\ehr_connected_systems.json", mode="w") as f:
        f.write(json.dumps(data))

    return {"message": "Connected labs and insurances data received successfully"}
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True, host="0.0.0.0")
    # if add reload then you also add the "main:app" else just put app
