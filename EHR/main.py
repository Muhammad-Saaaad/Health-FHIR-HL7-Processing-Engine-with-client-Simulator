from fastapi import FastAPI
import model

from database import engine
from Authentication import authentication
from Doctor import doctor

app = FastAPI(title="EHR System", version="1.0.0")
model.Base.metadata.create_all(bind=engine)

app.include_router(authentication.router)
app.include_router(doctor.router)

# set visit id into report id

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)
    # if add reload then you also add the "main:app" else just put app