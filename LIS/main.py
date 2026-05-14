import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from database import engine, local_session
import model
from api import auth, patient ,lab, engine_service, results, config
from rate_limiting import limiter, rate_limit_exceeded_handler
from sqlalchemy.exc import SAWarning
import warnings

warnings.filterwarnings("ignore", category=SAWarning)
os.makedirs("logs", exist_ok=True)

app = FastAPI(title="Laboratory Information System (LIS)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"], # allow all methods like POST, GET...
)

model.base.metadata.create_all(bind=engine) 

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(auth.router)
app.include_router(patient.router)
app.include_router(lab.router)
app.include_router(results.router)
app.include_router(engine_service.router)
app.include_router(config.router)

@app.get("/health/{system_id}")
def check_health(system_id: str):
    """
    Health-check endpoint for LIS service.

    **Response (200 OK):**
    - JSON object: `{ "message": "✔ LIS running" }`
    """
    db = local_session()
    try:
        server = db.query(model.Lab).filter(model.Lab.lab_id == system_id).first()
        if not server:
            raise HTTPException(status_code=404, detail={"message": f"Server with system_id '{system_id}' not found."})
        return {"message": f"✔ LIS running for system_id '{system_id}'"}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", port=8002, reload=True, host="0.0.0.0"
    )