import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
# from sqlalchemy.exc import SAWarning
# import warnings
 
from api import authentication, doctor, engine_service, visit_note, lab
from database import engine
import model
from rate_limiting import limiter, rate_limit_exceeded_handler

os.makedirs("logs", exist_ok=True)

# warnings.filterwarnings("ignore", category=SAWarning)
app = FastAPI(title="PHR System")
app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],
    allow_credentials= False,
    allow_headers=["*"],
    allow_methods=["*"]
)
model.Base.metadata.create_all(bind=engine)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(authentication.router)
app.include_router(doctor.router)
app.include_router(engine_service.router)
app.include_router(visit_note.router)
app.include_router(lab.router)

@app.get("/health")
def check_health():
    """
    Health-check endpoint for PHR service.

    **Response (200 OK):**
    - JSON object: `{ "message": "✔ PHR running" }`
    """
    return {"message": "✔ PHR running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8004, reload=True, host="0.0.0.0")
    # if add reload then you also add the "main:app" else just put app