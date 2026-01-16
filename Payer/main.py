from fastapi import FastAPI, status

from database import engine
import models

app = FastAPI(title="Hospital Insurance System")
models.Base.metadata.create_all(bind=engine)

@app.get("/", status_code=status.HTTP_200_OK)
def home():
    return {"message": "Final System is Live! 🚀 Go to /docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8003, reload=True)