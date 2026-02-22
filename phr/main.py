from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy.exc import SAWarning
# import warnings
 
from api import authentication
from database import engine
import model


# warnings.filterwarnings("ignore", category=SAWarning)
app = FastAPI(title="EHR System")
app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],
    allow_credentials= True,
    allow_headers=["*"],
    allow_methods=["*"]
)
model.Base.metadata.create_all(bind=engine)

app.include_router(authentication.router)

@app.get("/health")
def check_health():
    return {"message": "✔ PHR running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8004, reload=True, host="0.0.0.0")
    # if add reload then you also add the "main:app" else just put app