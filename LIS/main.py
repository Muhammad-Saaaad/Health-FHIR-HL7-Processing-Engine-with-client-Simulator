from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine
import model
from api import auth, patient ,lab, billing, engine_service

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"], # allow all methods like POST, GET...
)

model.base.metadata.create_all(bind=engine) 
app.include_router(auth.router)
app.include_router(patient.router)
app.include_router(lab.router)
app.include_router(billing.router)
app.include_router(engine_service.router)

@app.get("/health")
def check_health():
    return {"message": "sucessfull"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", port=8002, reload=True, host="0.0.0.0"
    )