from fastapi import FastAPI

from database import engine
import model
from api import auth, patient ,lab, billing

app = FastAPI()
model.base.metadata.create_all(bind=engine)  
app.include_router(auth.router)
app.include_router(patient.router)
app.include_router(lab.router)
app.include_router(billing.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", port=8002, reload=True
    )