from fastapi import FastAPI
import models

from database import engine

app = FastAPI(title="EMR Service", version="1.0.0")
models.base.metadata.create_all(bind=engine)

@app.get("/")
def health_check():
    return {"status": "EMR Service is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, port=8001)