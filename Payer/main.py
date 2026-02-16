from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware 

from database import engine
import models
from api import auth, claims, engine_service, patient, policy

app = FastAPI(title="Hospital Insurance System")
app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],
    allow_credentials= True,
    allow_headers=["*"],
    allow_methods=["*"]
)
models.Base.metadata.create_all(bind=engine)

@app.get("/health", status_code=status.HTTP_200_OK)
def home():
    return {"message": "Final System is Live! 🚀 Go to /docs"}

app.include_router(auth.router)
app.include_router(patient.router)
app.include_router(engine_service.router)
app.include_router(policy.router)
app.include_router(claims.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8003, reload=True)