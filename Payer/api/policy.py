from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import policy_schema as schema

router = APIRouter(tags=["Insurance_Policies"])

@router.post("/create_policy", status_code=status.HTTP_201_CREATED, tags=["Insurance_Policies"])
def create_policy(request: schema.PolicyCreate, db: Session = Depends(get_db)):

    if not db.query(models.Patient).filter(models.Patient.p_id == request.p_id).first():
        raise HTTPException(status_code=404, detail="Patient ID not found")
    
    is_user = db.query(models.SystemUser).filter(models.SystemUser.user_id == request.u_id).first()

    if not is_user:
        raise HTTPException(status_code=404, detail="Invalid user id")
        
    new_policy = models.InsurancePolicy(
        p_id=request.p_id,
        u_id=request.u_id,
        category_name=request.category_name,
        total_coverage=request.total_coverage,
        amount_used=request.amount_used,
        description=request.description,
    )
    db.add(new_policy)
    db.commit()
    db.refresh(new_policy)
    return new_policy

@router.get("/single_policy{policy_id}", status_code=200, response_model=schema.PolicyCreate, tags=["Insurance_Policies"])
def get_policy(policy_id : int , db: Session = Depends(get_db)):
    policy =  db.query(models.InsurancePolicy).filter(models.InsurancePolicy.policy_id == policy_id).first()
        
    if not policy:    
        raise HTTPException(status_code=404, detail="Insurance Policy ID not found")
    return policy

@router.get("/all_patients_per_policy_category{policy_category}", status_code=200, tags=["Insurance_Policies"])
def patients_per_policy_cat(policy_category : str, db: Session = Depends(get_db)):
    data = db.query(models.Patient).join(models.InsurancePolicy).filter(
        models.InsurancePolicy.category_name == policy_category).all()

    output = []
    for d in data:
        output.routerend({
            "p_id": d.p_id,
            "name": d.name,
            "cnic": d.cnic,
            "date_of_birth": d.date_of_birth,
            "policy_catrgory": policy_category
        })
    
    print(output)

    return output
