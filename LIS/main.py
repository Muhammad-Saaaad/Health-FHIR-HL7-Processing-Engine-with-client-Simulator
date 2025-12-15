from fastapi import FastAPI, status, HTTPException, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import engine, get_db
import model
from schemas import *

app = FastAPI()
model.base.metadata.create_all(bind=engine)

@app.post("/SignUp", status_code=status.HTTP_201_CREATED, tags=["user"])
def SignUp(user: SignUp, db: Session = Depends(get_db)):

    if db.query(model.User).filter(model.User.email == user.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email already exists")

    db_user = model.User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/Login", status_code=status.HTTP_200_OK, tags=["user"])
def login(request: Login, db: Session = Depends(get_db)):
    user = db.query(model.User).filter(model.User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email not exists")

    if user.password != request.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password not exists")
    
    return {"message": "Login sucessfull"}

@app.post("/reg_patients", response_model=Patient, status_code=status.HTTP_201_CREATED, tags=["patient"])
def register_patient(patient: Patient, db: Session = Depends(get_db)):

    if db.query(model.Patient).filter(model.Patient.cnic == patient.cnic).first(): 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cnic already exists")

    db_patient = model.Patient(**patient.model_dump())
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient

#################################################################

@app.get("/get_patients", response_model=list[Patient], tags=["patient"])
def get_all_patients(db: Session = Depends(get_db)):
    patients = db.query(model.Patient).all()
    return patients

@app.get("/patients/{pid}", response_model=Patient, tags=["patient"])
def get_patient_detail(pid: int, db: Session = Depends(get_db)):
    patient = db.get(model.Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

#################################################################

@app.post("/test_requests", response_model=TestRequestOut, status_code=status.HTTP_201_CREATED, tags=["Test Requests"])
def create_test_request(request: TestRequestCreate, db: Session = Depends(get_db)):
    
    is_patient = db.query(model.Patient).filter(model.Patient.cnic != request.patient_cnic).first()
    
    if not is_patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    db_request = model.LabTestRequest(
        patient_id = is_patient.pid,
        test_name = request.test_name,
        status = "Pending",
        decline_reason = None,
        locked_by = None,
        locked_at = None
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request

@app.get("/requests/pending", response_model=list[TestRequestOut], tags=["Test Requests"])
def get_pending_requests(db: Session = Depends(get_db)):
    return db.query(model.LabTestRequest).filter(model.LabTestRequest.status == "Pending").all()

@app.get("/requests/accepted/payment/paid", response_model=list[TestRequestOut], tags=["Test Requests"])
def get_accepted_requests(db: Session = Depends(get_db)):
    accepted_requests = db.query(model.LabTestRequest).join(model.LabTestBilling) \
        .filter(model.LabTestRequest.status == "Accepted", model.LabTestBilling.payment_status == "Paid").all()

    return accepted_requests

@app.put("/requests/{req_id}/status", response_model=TestRequestOut, tags=["Test Requests"])
def update_request_status(req_id: int, status_update: TestRequestStatusUpdate, db: Session = Depends(get_db)):
    updated_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == req_id).first()
    
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
    
    updated_request.status = status_update.status
    updated_request.decline_reason = status_update.decline_reason

    db.commit()
    db.refresh(updated_request)
    return updated_request

app.put("/requests/{req_id}/lock", response_model=TestRequestOut, tags=["Test Requests"])
def lock_test_request(req_id: int, user_id: int, db: Session = Depends(get_db)):
    
    current_request = db.get(model.LabTestRequest, req_id)
    if current_request and current_request.locked_by and current_request.locked_by != user_id:
        raise HTTPException(status_code=403, detail="Test is already locked by another technician.")
        
    current_request.locked_by = user_id
    current_request.locked_at = datetime.now()

    db.commit()
    db.refresh(current_request)
    
    updated_request = db.get(model.LabTestRequest, req_id)
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
        
    return updated_request

@app.put("/requests/{req_id}/unlock", response_model=TestRequestOut, tags=["Test Requests"])
def unlock_test_request(req_id: int, user_id: int, db: Session = Depends(get_db)):

    current_request = db.get(model.LabTestRequest, req_id)
    if current_request and current_request.locked_by and current_request.locked_by != user_id:
        raise HTTPException(status_code=403, detail="Test is already locked by another technician.")
        
    test_req = db.query(model.LabTestRequest).where(model.LabTestRequest.test_req_id == req_id).first()
    test_req.locked_by = user_id
    test_req.locked_at = datetime.now()

    db.commit()
    db.refresh(test_req)
    
    updated_request = db.get(model.LabTestRequest, req_id)
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
        
    return updated_request

#################################################################

@app.post("/billing/", response_model=BillingOut, status_code=status.HTTP_201_CREATED, tags=["Billing"])
def create_bill(b: BillingCreate, db: Session = Depends(get_db)):
    """Creates a new billing record."""
    if not db.get(model.Patient, b.pid) or not db.get(model.LabTestRequest, b.test_req_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient or Test Request not found.")

    if db.scalar(select(model.LabTestBilling).where(model.LabTestBilling.test_req_id == b.test_req_id)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A bill already exists for this test request.")

    bill = model.LabTestBilling(
        pid = b.pid,
        test_req_id = b.test_req_id,
        bill_amount = b.bill_amount,
        payment_status="Unpaid",
        create_at=datetime.now(),
        updated_at=datetime.now()
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill

@app.put("/billing/{bill_id}/pay", response_model=BillingOut, tags=["Billing"])
def update_payment(bill_id: int, db: Session = Depends(get_db)):
    """Marks a bill as 'Paid'."""
    bill = db.get(model.LabTestBilling, bill_id)
    if not bill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found.")
        
    bill.payment_status = "Paid"
    bill.updated_at = datetime.now()
    db.commit()
    db.refresh(bill)
    return bill

#################################################################

@app.post("/results/complete", status_code=status.HTTP_201_CREATED, tags=["Results"])
def add_complete_result(r_in: CompleteTestResultCreate, db: Session = Depends(get_db)):

    if not db.get(model.User, r_in.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User (Technician) ID not found.")
        
    req = db.get(model.LabTestRequest, r_in.test_req_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test Request not found.")
    
    if req.status != "Accepted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="test req is not accepted.")
    
    if db.query(model.LabTestBilling) \
        .filter(model.LabTestBilling.test_req_id == r_in.test_req_id).first().payment_status != "Paid":

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not paid.")

        
    if db.scalar(select(model.LabResult).where(model.LabResult.test_req_id == r_in.test_req_id)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Result already submitted for this request.")

    result = model.LabResult(
        user_id= r_in.user_id,
        test_req_id = r_in.test_req_id,
        description = r_in.description,
        created_at=datetime.now()
    )
    db.add(result)
    db.flush()

    db_mini_tests = []
    for mini_test_data in r_in.mini_tests:
        db_mini_tests.append(
            model.MiniLabResult(
                result_id=result.result_id,
                test_name = mini_test_data.test_name,
                normal_range = mini_test_data.normal_range,
                result_value = mini_test_data.result_value
            )
        )
    db.add_all(db_mini_tests)

    # 4. Update TestRequest status to Completed
    req.status = "Completed"
    db.add(req) 

    db.commit()
    return {"message": "result added"}

@app.post("/hl7/push")
async def hl7_push(req: Request):
    response = await req.json()
    print(response)

    ## debug hl7 and do something or call some functions
    return {"message":"data recieved"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", port=8002, reload=True
    )