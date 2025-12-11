from fastapi import FastAPI

import model
from database import engine

app = FastAPI()
model.base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", port=8002, reload=True
    )