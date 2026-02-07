from fastapi import FastAPI
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

# warnings.filterwarnings("ignore", category=SAWarning)
app = FastAPI(title="EHR System")
model.Base.metadata.create_all(bind=engine)

app.include_router(authentication.router)
app.include_router(lab.router)
app.include_router(patient.router)
app.include_router(visit_note.router)
# app.include_router(engine_service.router)

@app.get("/health")
def check_health():
    return {"message": "✔ EHR running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True, host="0.0.0.0")
    # if add reload then you also add the "main:app" else just put app