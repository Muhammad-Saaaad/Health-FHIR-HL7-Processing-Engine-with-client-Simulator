from datetime import datetime

from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.lab_schema import (
    TestRequestCreate, 
    TestRequestOut,
    TestRequestStatusUpdate,
    CompleteTestResultCreate
)

router = APIRouter(tags=["Test Requests"])

@router.post("/test_requests", response_model=TestRequestOut, status_code=status.HTTP_201_CREATED, tags=["Test Requests"])
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

@router.get("/requests/pending", response_model=list[TestRequestOut], tags=["Test Requests"])
def get_pending_requests(db: Session = Depends(get_db)):
    return db.query(model.LabTestRequest).filter(model.LabTestRequest.status == "Pending").all()

@router.get("/requests/accepted/payment/paid", response_model=list[TestRequestOut], tags=["Test Requests"])
def get_accepted_requests(db: Session = Depends(get_db)):
    accepted_requests = db.query(model.LabTestRequest).join(model.LabTestBilling) \
        .filter(model.LabTestRequest.status == "Accepted", model.LabTestBilling.payment_status == "Paid").all()

    return accepted_requests

@router.put("/requests/{req_id}/status", response_model=TestRequestOut, tags=["Test Requests"])
def update_request_status(req_id: int, status_update: TestRequestStatusUpdate, db: Session = Depends(get_db)):
    updated_request = db.query(model.LabTestRequest).filter(model.LabTestRequest.test_req_id == req_id).first()
    
    if not updated_request:
        raise HTTPException(status_code=404, detail="Test Request not found")
    
    updated_request.status = status_update.status
    updated_request.decline_reason = status_update.decline_reason

    db.commit()
    db.refresh(updated_request)
    return updated_request

router.put("/requests/{req_id}/lock", response_model=TestRequestOut, tags=["Test Requests"])
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

@router.put("/requests/{req_id}/unlock", response_model=TestRequestOut, tags=["Test Requests"])
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


@router.post("/results/complete", status_code=status.HTTP_201_CREATED, tags=["Results"])
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

        
    if db.query(model.LabResult).filter(model.LabResult.test_req_id == r_in.test_req_id).first():
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