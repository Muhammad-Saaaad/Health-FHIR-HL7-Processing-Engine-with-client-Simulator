from fastapi import FastAPI
from sqlalchemy.exc import SAWarning
import warnings
 
from database import engine
import model
from api import (
    authentication, 
    lab, 
    patient, 
    visit_note, 
)

warnings.filterwarnings("ignore", category=SAWarning)
app = FastAPI(title="EHR System", version="1.0.0")
model.Base.metadata.create_all(bind=engine)

app.include_router(authentication.router)
app.include_router(lab.router)
app.include_router(patient.router)
app.include_router(visit_note.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)
    # if add reload then you also add the "main:app" else just put app