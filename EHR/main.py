from fastapi import FastAPI, status, Depends, HTTPException
import model

from database import engine
from Authentication import authentication
from Doctor import doctor

app = FastAPI(title="EHR System", version="1.0.0")
model.base.metadata.create_all(bind=engine)

app.include_router(authentication.router)
app.include_router(doctor.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)
    # if add reload then you also add the "main:app" else just put app