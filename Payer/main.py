import os

from fastapi import FastAPI, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware 
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from database import engine, SessionLocal
import models
from api import auth, claims, engine_service, patient, policy, config
from rate_limiting import limiter, rate_limit_exceeded_handler
from sqlalchemy.exc import SAWarning
import warnings

warnings.filterwarnings("ignore", category=SAWarning)
os.makedirs(r"logs", exist_ok=True)

app = FastAPI(title="Hospital Insurance System")
app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],
    allow_credentials= False,
    allow_headers=["*"],
    allow_methods=["*"]
)
models.Base.metadata.create_all(bind=engine)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(patient.router)
app.include_router(engine_service.router)
app.include_router(policy.router)
app.include_router(claims.router)
app.include_router(config.router)

@app.get("/health/{system_id}")
def check_health(system_id: str):
    """
    Health-check endpoint for Payer service.

    **Response (200 OK):**
    - JSON object: `{ "message": "✔ Payer running" }`
    """
    db = SessionLocal()
    try:
        server = db.query(models.Insurance).filter(models.Insurance.insurance_id == system_id).first()
        if not server:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": f"Server with system_id '{system_id}' not found."})
        return {"message": f"✔ Payer running for system_id '{system_id}'"}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8003, reload=True)