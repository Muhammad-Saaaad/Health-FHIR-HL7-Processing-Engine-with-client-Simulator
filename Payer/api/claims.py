from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import claims_schema as schema

router = APIRouter(tags=["Claims"])

@router.post("/submit_claim", response_model=schema.PatientClaimDisplay, status_code=status.HTTP_201_CREATED, tags=["Claims"])
def submit_claim(request: schema.PatientClaimCreate, db: Session = Depends(get_db)):
    
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
    claim =  db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()

    if not claim:
        raise HTTPException(status_code=404, detail="Claim ID not found")
    
    return claim

@router.put("/change_claim_status{claim_id}/{claim_status}", status_code=status.HTTP_202_ACCEPTED, tags=['Claims'])
def claim_status(claim_id : int, claim_status: str, db: Session = Depends(get_db)):

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