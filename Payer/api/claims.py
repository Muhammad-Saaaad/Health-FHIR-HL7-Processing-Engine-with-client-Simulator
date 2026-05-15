import asyncio
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response 
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.orm.attributes import flag_modified

from database import get_db
import models
from schemas import claims_schema as schema
from rate_limiting import limiter
from .engine_service import claim_response_to_engine
from .logging_config import get_logger

logger = get_logger('Payer.api.claims', logfile=r'logs\payer_api.log')

router = APIRouter(tags=["Claims"])

@router.get("/expnse_breakdown/patient_id/{pid}/policy_id/{policy_id}", response_model=list[schema.ExpenseBreakdown])
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def expense_breakdown(pid: int, policy_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Return an expense breakdown for all claims linked to a patient and policy.

    **Path Parameters:**
    - `pid` (int, required): Patient primary key.
    - `policy_id` (int, required): Insurance policy primary key.

    **Response (200 OK):**
    Returns `list[schema.ExpenseBreakdown]`. Each entry includes:
    - `claim_date` (datetime): claim creation timestamp
    - `service_included` (bool): 
    - `tests_included` (bool): 
    - `total_amount` (float): billed amount
    - `status` (str): current claim status

    **Error Responses:**
    - `404 Not Found`: Patient ID does not exist.
    - `404 Not Found`: Policy ID does not exist.
    - `404 Not Found`: No claims found for this patient-policy pair.
    """
    logger.info(f"expense_breakdown called: pid={pid} policy_id={policy_id}")
    is_patient = db.get(models.Patient, pid)
    if not is_patient:
        logger.error(f"expense_breakdown: patient id {pid} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient ID not found")

    is_policy = db.get(models.InsurancePolicy, policy_id)
    if not is_policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy ID not found")
    
    claims = db.query(models.PatientClaim).filter(models.PatientClaim.policy_id == policy_id, models.PatientClaim.pid == pid).all()

    claim_expense = []
    for claim in claims:
        claim_expense.append(
            schema.ExpenseBreakdown(
                claim_date=claim.created_at,
                service_included=claim.service_included,
                tests_included=claim.tests_included,
                total_amount=float(claim.bill_amount),
                status=claim.claim_status
            )
        )
    logger.info(f"expense_breakdown returning {len(claim_expense)} records for pid={pid} policy_id={policy_id}")
    return claim_expense

@router.get("/get_all_claims/{insurance_id}", response_model=list[schema.AllClaims])
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def get_all_pending_claims(insurance_id: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all claims that are currently in "Pending" status.

    **Path Parameters:**
    - `insurance_id` (str): Insurance company ID used to filter pending claims.

    **Response (200 OK):**
    Returns `list[schema.AllClaims]`. Each item includes:
    - `claim_id` (int)
    - `nic` (str | null)
    - `policy_number` (int)
    - `name` (str)
    - `created_at` (datetime | null)

    **Note:**
    - Only claims with `claim_status == "Pending"` are returned.
    - Claims are returned only when the linked patient has the provided `insurance_id`.
    - Returns an empty list if there are no pending claims.
    """
    logger.info(f"get_all_pending_claims called for insurance_id={insurance_id}")
    all_claims = (
        db.query(models.PatientClaim)
        .join(models.Patient, models.Patient.pid == models.PatientClaim.pid)
        .filter(
            models.PatientClaim.claim_status == "Pending",
            models.Patient.insurance_id == insurance_id
        )
        .all()
    )
    claims = [
        {
            "claim_id" : claim.claim_id,
            "nic": claim.patient.nic,
            "policy_number": claim.policy_id,
            "name": claim.patient.name,
            "created_at": claim.created_at
        }
        for claim in all_claims
    ]

    logger.info(f"get_all_pending_claims returning {len(claims)} claims for insurance_id={insurance_id}")
    return claims

@router.get("/get_single_claim{claim_id}", response_model=schema.PatientClaimDisplay)
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def get_single_claims(claim_id : int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve the complete details of a specific claim by its ID.

    **Path Parameters:**
    - `claim_id` (int, required): The unique identifier of the claim to retrieve.

    **Response (200 OK):**
    Returns `schema.PatientClaimDisplay` including:
    - `claim_id` (int)
    - `policy_id` (int)
    - `pid` (int)
    - `patient_name` (str)
    - `patient_phone_no` (str)
    - `gender` (str)
    - `bill_amount` (float)
    - `total_coverage` (float)
    - `amount_used` (float)
    - `service_included` (bool)
    - `tests_included` (bool)

    **Error Responses:**
    - `404 Not Found`: No claim exists with the given `claim_id`
    """
    logger.info(f"get_single_claims called for claim_id={claim_id}")
    claim =  db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()

    if not claim:
        logger.error(f"get_single_claims: claim_id={claim_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim ID not found")
    
    logger.info(f"get_single_claims found claim_id={claim_id}")
    return claim

@router.put("/change_claim_status{claim_id}/{claim_status}/user/{user_id}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
async def claim_status(user_id: int, claim_id : int, claim_status: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Update the status of a claim and automatically add the bill amount to the associated policy's usage.

    **Path Parameters:**
    - `claim_id` (int, required): The unique identifier of the claim to update.
    - `claim_status` (str, required): The new status to set (e.g., "Pending", "Approved", "Rejected").
    - `user_id` (int, required): The unique identifier of the user updating the claim status.

    **Response (202 Accepted):**
    Returns a confirmation message:
    - `message`: e.g., "status set to Approved"

    **Side Effects:**
    - Updates the associated `InsurancePolicy.amount_used` by adding the claim's `bill_amount` to it.

    **Error Responses:**
    - `404 Not Found`: No claim exists with the given `claim_id`
    - `404 Not Found`: The policy linked to the claim was not found
    """
    logger.info(f"claim_status update requested: claim_id={claim_id} status={claim_status}")
    if not claim_status in ('Approved', 'Rejected'):
        logger.error(f"claim_status invalid status provided: {claim_status}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status should be either Approved or Rejected")

    claim = db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()

    if not claim:
        logger.error(f"claim_status: claim_id={claim_id} not found")
        raise HTTPException(status_code=404, detail="claim id not found")
    
    if claim.locked_by_user_id is None or claim.locked_by_user_id != user_id:
        logger.warning(f"claim_status: claim_id={claim_id} is not locked by user_id={user_id}, cannot update status")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="claim is not locked for processing")

    if claim.locked_by_user_id != user_id:
        logger.warning(f"claim_status: claim_id={claim_id} is locked by another user, cannot update status")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="claim is locked by another user")
    
    claim.claim_status = claim_status

    test_req = db.query(models.InsurancePolicy).filter(models.InsurancePolicy.policy_id == claim.policy_id).first()

    if not test_req:
        logger.error(f"claim_status: policy for claim_id={claim_id} not found")
        raise HTTPException(status_code=404, detail="claim has not test request id")
    
    user = db.get(models.Patient, test_req.pid)
    insurance = db.get(models.Insurance, user.insurance_id)
    
    msg_id = str(uuid4())
    hl7_msg = f"MSH|^~\\&|PAYER||EHR||20260502153000|{msg_id}|ACK^P03||P|2.5\n"
    hl7_msg += f"PID|1||{user.nic}\n"
    hl7_msg += f"PV1|1||||||||||||||||||{claim.vid}\n"
    hl7_msg += f"MSA|1|AA|{claim_status}\n"

    # 4. Update TestRequest status to Completed
    config_data= db.query(models.Config).filter(models.Config.sent_to_engine == False) \
            .order_by(desc(models.Config.config_id)).first()
    
    if config_data and config_data.hold_flag: # if we have to hold the data
        history_hospital = config_data.history.get(insurance.name, {})

        if history_hospital:
            history_hospital["submit-claim-response"] = history_hospital.get("submit-claim-response", 0) + 1
        else:
            config_data.history[insurance.name] = history_hospital
            config_data.history[insurance.name]["submit-claim-response"] = 1
        
        endpoint_already_added = False
        for endpoint in config_data.data:
            if endpoint.get("system_id") == insurance.insurance_id and endpoint.get("/send/claim_response"): # if endpoint exists in config.
                endpoint["/send/claim_response"].append(hl7_msg)
                endpoint_already_added = True
                break
        
        if not endpoint_already_added:
            config_data.data.append(
                {   
                    "system_id": insurance.insurance_id,
                    "/send/claim_response": [hl7_msg]
                }
            )

        flag_modified(config_data, "history")
        flag_modified(config_data, "data")

        test_req.status = "Completed"
        db.add(test_req)
        db.commit()
        logger.info(f"Data added to config for insurance {insurance.name} due to hold flag. Current history: {config_data.history}")
        return {"message": "data added to config due to hold flag"}

    logger.info(f"claim_status sending HL7 message for claim_id={claim_id}: {hl7_msg}")
    asyncio.create_task(claim_response_to_engine("http://127.0.0.1:9000/send/claim_response", hl7_msg, test_req.insurance_id))

    logger.info(f"claim_status: Successfully sent claim response to engine for claim_id={claim_id}")
    test_req.amount_used = test_req.amount_used + claim.bill_amount
    db.add(test_req)
    db.add(claim)

    db.commit()
    return {"message": f"status set to {claim_status}"}

@router.put("/lock_claim{claim_id}/by{user_id}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def claim_lock(claim_id : int, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
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
        logger.error(f"claim_lock: claim_id={claim_id} not found")
        raise HTTPException(status_code=404, detail="claim id not found")
    
    user = db.query(models.SystemUser).filter(models.SystemUser.user_id == user_id).first()
    if not user:
        logger.error(f"claim_lock: user_id={user_id} not found")
        raise HTTPException(status_code=404, detail="user id not found")
    
    if claim.locked_by_user_id != None and claim.locked_by_user_id != user_id:
        logger.warning(f"claim_lock: claim_id={claim_id} already locked by another user")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="claim already locked")

    claim.locked_by_user_id = user_id
    claim.locked_at = datetime.now()
    
    db.add(claim)
    db.commit()

    logger.info(f"claim_lock: claim_id={claim_id} locked by user_id={user_id}")
    return {"message": f"claim locked by {user.user_name}"}

@router.put("/unlock_claim{claim_id}/by{user_id}", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
def claim_unlock(claim_id : int, user_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Unlock a claim to release it from processing so it can be worked on again.

    **Path Parameters:**
    - `claim_id` (int, required): The unique identifier of the claim to unlock.
    - `user_id` (int, required): The ID of the user requesting the unlock.

    **Response (202 Accepted):**
    Returns a confirmation message:
    - `message`: e.g., "claim unlocked by john_doe"

    **Constraints:**
    - Only the user who originally locked the claim can unlock it (if currently locked).
    - If the claim is already unlocked, the operation succeeds (idempotent).

    **Error Responses:**
    - `404 Not Found`: No claim exists with the given `claim_id`
    - `404 Not Found`: No user exists with the given `user_id`
    - `409 Conflict`: The claim is locked by another user
    """
    claim = db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()
    if not claim:
        logger.error(f"claim_unlock: claim_id={claim_id} not found")
        raise HTTPException(status_code=404, detail="claim id not found")

    user = db.query(models.SystemUser).filter(models.SystemUser.user_id == user_id).first()
    if not user:
        logger.error(f"claim_unlock: user_id={user_id} not found")
        raise HTTPException(status_code=404, detail="user id not found")
    
    # If claim is locked by another user, reject the unlock
    if claim.locked_by_user_id is not None and claim.locked_by_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="claim locked by another user")
    
    claim.locked_by_user_id = None
    claim.locked_at = None

    db.add(claim)
    db.commit()
    db.refresh(claim)
    logger.info(f"claim_unlock: claim_id={claim_id} unlocked by user_id={user_id}")
    return {"message": f"claim unlocked by {user.user_name}"}
