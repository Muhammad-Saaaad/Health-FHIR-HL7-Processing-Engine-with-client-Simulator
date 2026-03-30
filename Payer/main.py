from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware 
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from database import engine
import models
from api import auth, claims, engine_service, patient, policy
from rate_limiting import limiter, rate_limit_exceeded_handler

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

@app.get("/health", status_code=status.HTTP_200_OK)
def home():
    return {"message": "Final System is Live! 🚀 Go to /docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8003, reload=True)