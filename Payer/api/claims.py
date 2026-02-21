from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import claims_schema as schema

router = APIRouter(tags=["Claims"])

@router.post("/submit_claim", response_model=schema.PatientClaimDisplay, status_code=status.HTTP_201_CREATED, tags=["Claims"])
def submit_claim(request: schema.PatientClaimCreate, db: Session = Depends(get_db)):
    """
    Submit a new insurance claim for a patient.

    **Request Body:**
    - `policy_id` (int, required): Valid insurance policy ID. Must exist in the system.
    - `patient_id` (int, required): Valid patient ID. Must exist in the system.
    - `service_name` (str, required): Name of the service/treatment provided (e.g., "Surgery", "Consultation").
    - `bill_amount` (float, required): Total amount to be claimed. Must be greater than 0.
    - `provider_phone_no` (str, optional): Contact phone number of the service provider.

    **Response (201 Created):**
    Returns the newly created claim object including:
    - `claim_id`: Auto-generated unique claim identifier
    - `claim_status`: Defaults to "Pending" on creation
    - `created_at`: Timestamp of when the claim was submitted

    **Error Responses:**
    - `404 Not Found`: `policy_id` or `patient_id` does not exist in the system
    - `422 Unprocessable Entity`: Missing required fields or invalid data types
    """
    policy = db.query(models.InsurancePolicy).filter(models.InsurancePolicy.policy_id == request.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy ID not found")
    
    patient = db.query(models.Patient).filter(models.Patient.p_id == request.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient ID not found")

    new_claim = models.PatientClaim(
        policy_id=request.policy_id,
        patient_id = request.patient_id,
        service_name=request.service_name,
        bill_amount=request.bill_amount,
        provider_phone_no=request.provider_phone_no
    )
    db.add(new_claim)
    db.commit()
    db.refresh(new_claim)
    return new_claim

@router.get("/get_all_claims", response_model=list[schema.AllClaims], status_code=status.HTTP_200_OK, tags=["Claims"])
def get_all_pending_claims(db: Session = Depends(get_db)):
    """
    Retrieve all claims that are currently in "Pending" status.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of pending claims. Each item includes:
    - `claim_id`: Unique claim identifier
    - `name`: Patient's full name
    - `service_name`: Name of the service/treatment
    - `phone_no`: Patient's contact phone number
    - `created_at`: Timestamp of claim submission

    **Note:**
    - Only claims with `claim_status == "Pending"` are returned.
    - Returns an empty list if there are no pending claims.
    """
    all_claims = db.query(models.PatientClaim).filter(models.PatientClaim.claim_status == 'Pending').all()
    claims =[ 
        {
            "claim_id" : claim.claim_id,
            "name": claim.patient.name,
            "service_name": claim.service_name,
            "phone_no": claim.patient.phone_no,
            "created_at": claim.created_at
        }
        for claim in all_claims # called list comprehension. cleaner way
    ]

    return claims

@router.get("/claims_per_patient{pid}", response_model=schema.ClaimsPerPatient, status_code=200, tags=["Claims"])
def claims_per_patient(pid : int , db: Session = Depends(get_db)):
    """
    Get all claims associated with a specific patient.

    **Path Parameters:**
    - `pid` (int, required): The patient's unique ID.

    **Response (200 OK):**
    Returns an object containing:
    - `patient_id`: The patient's ID
    - `all_claims`: Array of claim objects, each with:
        - `claim_id`: Unique claim identifier
        - `name`: Patient's full name
        - `service_name`: Name of the service/treatment
        - `phone_no`: Patient's contact phone number
        - `created_at`: Timestamp of claim submission

    **Note:**
    - Returns an object with an empty `all_claims` array if the patient has no claims.
    - Does not validate whether the patient ID exists; simply returns no data if not found.
    """
    data = db.query(models.PatientClaim).filter(models.PatientClaim.patient_id == pid).all()

    output = [
        {
            "claim_id" : claim.claim_id,
            "name": claim.patient.name,
            "service_name": claim.service_name,
            "phone_no": claim.patient.phone_no,
            "created_at": claim.created_at
        }
        for claim in data 
    ]
    out_data = {"patient_id": pid, "all_claims": output}
    return out_data

@router.get("/get_single_claim{claim_id}", response_model=schema.PatientClaimDisplay, status_code=status.HTTP_200_OK, tags=["Claims"])
def get_single_claims(claim_id : int, db: Session = Depends(get_db)):
    """
    Retrieve the complete details of a specific claim by its ID.

    **Path Parameters:**
    - `claim_id` (int, required): The unique identifier of the claim to retrieve.

    **Response (200 OK):**
    Returns the full claim object including:
    - `claim_id`: Unique claim identifier
    - `policy_id`: Associated insurance policy ID
    - `patient_id`: Associated patient ID
    - `service_name`: Name of the service/treatment
    - `bill_amount`: The total claimed amount
    - `claim_status`: Current status (e.g., "Pending", "Approved", "Rejected", "Paid")
    - `provider_phone_no`: Provider contact number (if provided)
    - `created_at`: Timestamp of claim submission

    **Error Responses:**
    - `404 Not Found`: No claim exists with the given `claim_id`
    """
    claim =  db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()

    if not claim:
        raise HTTPException(status_code=404, detail="Claim ID not found")
    
    return claim

@router.put("/change_claim_status{claim_id}/{claim_status}", status_code=status.HTTP_202_ACCEPTED, tags=['Claims'])
def claim_status(claim_id : int, claim_status: str, db: Session = Depends(get_db)):
    """
    Update the status of a claim and automatically add the bill amount to the associated policy's usage.

    **Path Parameters:**
    - `claim_id` (int, required): The unique identifier of the claim to update.
    - `claim_status` (str, required): The new status to set (e.g., "Pending", "Approved", "Rejected", "Paid").

    **Response (202 Accepted):**
    Returns a confirmation message:
    - `message`: e.g., "status set to Approved"

    **Side Effects:**
    - Updates the associated `InsurancePolicy.amount_used` by adding the claim's `bill_amount` to it.

    **Error Responses:**
    - `404 Not Found`: No claim exists with the given `claim_id`
    - `404 Not Found`: The policy linked to the claim was not found
    """
    claim = db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()

    if not claim:
        raise HTTPException(status_code=404, detail="claim id not found")
    
    claim.claim_status = claim_status

    test_req = db.query(models.InsurancePolicy).filter(models.InsurancePolicy.policy_id == claim.policy_id).first()

    if not test_req:
        raise HTTPException(status_code=404, detail="claim has not test request id")
    
    test_req.amount_used = test_req.amount_used + claim.bill_amount

    db.add(test_req)
    db.add(claim)

    db.commit()
    db.refresh(claim)

    return {"message": f"status set to {claim_status}"}

@router.put("/lock_claim{claim_id}/by{user_id}", status_code=status.HTTP_202_ACCEPTED, tags=['Claims'])
def claim_lock(claim_id : int, user_id: int, db: Session = Depends(get_db)):
    """
    Lock a claim to a specific user to prevent concurrent modifications during processing.

    **Path Parameters:**
    - `claim_id` (int, required): The unique identifier of the claim to lock.
    - `user_id` (int, required): The ID of the user who is locking the claim.

    **Response (202 Accepted):**
    Returns a confirmation message:
    - `message`: e.g., "claim locked by john_doe"

    **Constraints:**
    - A user can re-lock a claim they have already locked (idempotent).
    - A different user cannot lock a claim that is already locked by someone else.

    **Error Responses:**
    - `404 Not Found`: No claim exists with the given `claim_id`
    - `404 Not Found`: No user exists with the given `user_id`
    - `409 Conflict`: The claim is already locked by a different user
    """
    claim = db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="claim id not found")
    
    user = db.query(models.SystemUser).filter(models.SystemUser.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user id not found")
    
    if claim.locked_by_user_id != None and claim.locked_by_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="claim already locked")
    
    claim.locked_by_user_id = user_id
    claim.locked_at = datetime.now()

    db.commit()
    db.refresh(claim)

    return {"message": f"claim locked by {user.user_name}"}

@router.put("/unlock_claim{claim_id}/by{user_id}", status_code=status.HTTP_202_ACCEPTED, tags=['Claims'])
def claim_unlock(claim_id : int, user_id: int, db: Session = Depends(get_db)):
    """
    Unlock a claim to release it from processing so it can be worked on again.

    **Path Parameters:**
    - `claim_id` (int, required): The unique identifier of the claim to unlock.
    - `user_id` (int, required): The ID of the user requesting the unlock.

    **Response (202 Accepted):**
    Returns a confirmation message:
    - `message`: e.g., "claim unlocked by john_doe"

    **Constraints:**
    - Only the user who originally locked the claim can unlock it.
    - Cannot unlock a claim that is already unlocked.

    **Error Responses:**
    - `404 Not Found`: No claim exists with the given `claim_id`
    - `404 Not Found`: No user exists with the given `user_id`
    - `409 Conflict`: The claim is already unlocked (not locked by anyone)
    """
    claim = db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="claim id not found")
    
    
    user = db.query(models.SystemUser).filter(models.SystemUser.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user id not found")
    
    if claim.locked_by_user_id == None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="claim already unlocked")
    
    claim.locked_by_user_id = None
    claim.locked_at = None

    db.commit()
    db.refresh(claim)

    return {"message": f"claim unlocked by {user.user_name}"}