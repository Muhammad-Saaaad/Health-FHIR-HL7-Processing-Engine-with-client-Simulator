from datetime import datetime

from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from schemas.billing_schema import BillingCreate, BillingOut

router = APIRouter(tags=["Billing"])

@router.post("/billing/", response_model=BillingOut, status_code=status.HTTP_201_CREATED, tags=["Billing"])
def create_bill(b: BillingCreate, db: Session = Depends(get_db)):
    """
    Create a new billing record for a lab test request.

    **Request Body:**
    - `pid` (int, required): Patient ID to associate the bill with. Must exist in the system.
    - `test_req_id` (int, required): Lab test request ID to bill for. Must exist in the system.
    - `bill_amount` (float, required): Total amount to charge for the lab test.

    **Response (201 Created):**
    Returns the newly created billing record including:
    - `bill_id`: Auto-generated unique bill identifier
    - `pid`: Associated patient ID
    - `test_req_id`: Associated test request ID
    - `bill_amount`: Charged amount
    - `payment_status`: Defaults to "Unpaid" on creation
    - `create_at`: Timestamp of bill creation
    - `updated_at`: Timestamp of last update

    **Constraints:**
    - Both `pid` and `test_req_id` must refer to existing records.
    - Only one bill can exist per test request. Duplicate billing is rejected.

    **Error Responses:**
    - `404 Not Found`: Patient or test request not found
    - `400 Bad Request`: A bill already exists for this test request
    """
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
    """
    Mark an existing bill as paid.

    **Path Parameters:**
    - `bill_id` (int, required): The unique identifier of the bill to mark as paid.

    **Response (200 OK):**
    Returns the updated billing record with:
    - `payment_status`: Updated to "Paid"
    - `updated_at`: Updated timestamp reflecting when the payment was recorded

    **Note:**
    - This endpoint does not require a request body. It simply flips `payment_status` to "Paid".
    - No payment amount or method is validated; it is assumed payment is confirmed externally.

    **Error Responses:**
    - `404 Not Found`: No bill exists with the given `bill_id`
    """
    bill = db.get(model.LabTestBilling, bill_id)
    if not bill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bill not found.")
        
    bill.payment_status = "Paid"
    bill.updated_at = datetime.now()
    db.commit()
    db.refresh(bill)
    return bill
