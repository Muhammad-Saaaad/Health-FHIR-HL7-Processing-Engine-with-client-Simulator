import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from database import engine
import model
from api import auth, patient ,lab, engine_service, results
from rate_limiting import limiter, rate_limit_exceeded_handler

os.makedirs("logs", exist_ok=True)

app = FastAPI()

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

@app.get("/health")
def check_health():
    """
    Health-check endpoint for LIS service.

    **Response (200 OK):**
    - JSON object: `{ "message": "sucessfull" }`
    """
    return {"message": "sucessfull"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", port=8002, reload=True, host="0.0.0.0"
    )