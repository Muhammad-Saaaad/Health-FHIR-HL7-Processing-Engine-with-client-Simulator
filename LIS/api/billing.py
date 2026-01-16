from datetime import datetime

from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.billing_schema import BillingCreate, BillingOut

router = APIRouter(tags=["Billing"])

@router.post("/billing/", response_model=BillingOut, status_code=status.HTTP_201_CREATED, tags=["Billing"])
def create_bill(b: BillingCreate, db: Session = Depends(get_db)):
    """Creates a new billing record."""
    if not db.get(model.Patient, b.pid) or not db.get(model.LabTestRequest, b.test_req_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient or Test Request not found.")

    if db.query(model.LabTestBilling).filter(model.LabTestBilling.test_req_id == b.test_req_id).first():
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

@router.put("/billing/{bill_id}/pay", response_model=BillingOut, tags=["Billing"])
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
