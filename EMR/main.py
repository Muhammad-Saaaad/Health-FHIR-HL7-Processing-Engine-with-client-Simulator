from fastapi import FastAPI, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import session
import model

from database import engine, get_db
from model import Doctor
from schemas import fetchDoctors

app = FastAPI(title="EMR Service", version="1.0.0")
model.base.metadata.create_all(bind=engine)

@app.get("/")
def health_check():
    return {"status": "EMR Service is running"}

@app.get("/doctors", response_model=list[fetchDoctors], status_code=status.HTTP_200_OK)
def all_doctors(db :session = Depends(get_db)):
    try:
        all_docs = db.query(Doctor).all()

        if all_docs == []:
            return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=all_docs)
        return all_docs
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@app.post("/doctors", response_model=fetchDoctors, status_code=status.HTTP_201_CREATED)
def create_doctor(doctor: fetchDoctors, db :session = Depends(get_db)):
    doctor = fetchDoctors(**doctor.model_dump())
    new_doctor = Doctor(
        name = doctor.name,
        email = doctor.email,
        password = doctor.password,
        specialization = doctor.specialization,
        phone_no = doctor.phone_no,
        date_join = doctor.date_join,
        about = doctor.about
    )
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    return new_doctor

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)
    # if add reload then you also add the "main:app" else just put app