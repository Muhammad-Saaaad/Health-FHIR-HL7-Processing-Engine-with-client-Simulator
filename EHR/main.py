import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
# from sqlalchemy.exc import SAWarning
# import warnings
 
from database import engine
import model
from api import (
    authentication, 
    lab, 
    patient, 
    visit_note,
    # engine_service
)
from rate_limiting import limiter, rate_limit_exceeded_handler

# warnings.filterwarnings("ignore", category=SAWarning)
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
# app.include_router(engine_service.router)

@app.get("/health")
def check_health():
    """
    Health-check endpoint for EHR service.

    **Response (200 OK):**
    - JSON object: `{ "message": "✔ EHR running" }`
    """
    return {"message": "✔ EHR running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True, host="0.0.0.0")
    # if add reload then you also add the "main:app" else just put app