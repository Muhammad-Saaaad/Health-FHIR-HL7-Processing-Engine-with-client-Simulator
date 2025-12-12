from fastapi import FastAPI, status, HTTPException, Depends
from sqlalchemy.orm import session

from database import engine, get_db
import model
from schemas import *

app = FastAPI()
model.base.metadata.create_all(bind=engine)

# Register Patient
@app.post("/reg_patients", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def register_patient(patient: PatientCreate, db: session = Depends(get_db)):
    db_patient = model.Patient(**patient.model_dump())
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient

# API 3: Get Patient List
@app.get("/get_patients", response_model=list[PatientOut])
def get_all_patients(db: session = Depends(get_db)):
    patients = db.query(model.Patient).all()
    return patients

# API 4: Get Patient Detail
@app.get("/patients/{pid}", response_model=PatientOut)
def get_patient_detail(pid: int, db: session = Depends(get_db)):
    patient = db.get(model.Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

# =========================================================================
# II. Test Request/Order Management APIs (APIs 5, 6, 7, 8)
# =========================================================================

# API 5: Create Test Order
@app.post("/requests", response_model=TestRequestOut, status_code=status.HTTP_201_CREATED)
def create_test_request(request: TestRequestCreate, db: session = Depends(get_db)):
    if not db.get(model.Patient, request.patient_id):
        raise HTTPException(status_code=404, detail="Patient ID not found")
        
    db_request = model.LabTestRequest(**request.model_dump())
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request

# API 6: Get Pending Tests
@app.get("/requests/pending", response_model=list[TestRequestOut])
def get_pending_requests(db: session = Depends(get_db)):
    pending_requests = db.query(model.LabTestRequest).where(model.LabTestRequest.status == "Pending").all()
    return pending_requests

# API 7: Update Status (Accept/Decline/Complete) # run when you recieve the response from payer via engine
# @app.put("/requests/{req_id}/status", response_model=TestRequestOut)
# def update_request_status(req_id: int, status_update: TestRequestStatusUpdate, db: session = Depends(get_db)):
    
#     db.execute(
#         update(model.LabTestRequest)
#         .where(model.LabTestRequest.test_req_id == req_id)
#         .values(
#             status=status_update.status,
#             decline_reason=status_update.decline_reason,
#         )
#     )
#     db.commit()
    
#     updated_request = db.get(model.LabTestRequest, req_id)
#     if not updated_request:
#         raise HTTPException(status_code=404, detail="Test Request not found")
        
#     return updated_request

# API 8: Lock Request
@app.put("/requests/{req_id}/lock", response_model=TestRequestOut)
def lock_test_request(req_id: int, user_id: int, db: session = Depends(get_db)):
    current_request = db.get(model.LabTestRequest, req_id)
    if current_request and current_request.locked_by and current_request.locked_by != user_id:
        raise HTTPException(status_code=403, detail="Test is already locked by another technician.")
        
    test_req = db.query(model.LabTestRequest).where(model.LabTestRequest.test_req_id == req_id).first()
    test_req.locked_by = user_id
    test_req.locked_at = datetime.now()

    # .values(
    #         locked_by=user_id,
    #         locked_at=datetime.now(),
    #     )
    # )
    db.commit()
    db.refresh(test_req)
    
    updated_request = db.get(model.LabTestRequest, req_id)
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
        
    return updated_request

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", port=8002, reload=True
    )