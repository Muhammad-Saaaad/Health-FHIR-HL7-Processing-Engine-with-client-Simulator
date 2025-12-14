from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import session

from database import engine, get_db
import models
import schemas

app = FastAPI(
    title="Hospital Insurance System",
    description="Complete API: Signup/Login, Patients, Policies, Claims",
    version="Final"
)

models.Base.metadata.create_all(bind=engine)

@app.get("/", status_code=status.HTTP_200_OK)
def home():
    return {"message": "Final System is Live! 🚀 Go to /docs"}



@app.post("/signup", response_model=schemas.SystemUserDisplay, status_code=status.HTTP_201_CREATED, tags=["Users"])
def signup_user(request: schemas.SystemUserCreate, db: session = Depends(get_db)):

    existing_user = db.query(models.SystemUser).filter(models.SystemUser.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")


    new_user = models.SystemUser(
        user_name=request.user_name,
        email=request.email,
        password=request.password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", status_code=status.HTTP_200_OK, tags=["Users"])
def login_user(request: schemas.LoginRequest, db: session = Depends(get_db)):
    user = db.query(models.SystemUser).filter(models.SystemUser.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid Email")
    
    if user.password != request.password:
        raise HTTPException(status_code=404, detail="Invalid Password")

    return {
        "message": "Login Successful",
        "user_id": user.user_id,
        "user_name": user.user_name
    }


@app.post("/reg_patient", response_model=schemas.PatientDisplay, status_code=status.HTTP_201_CREATED, tags=["Patients"])
def register_patient(request: schemas.PatientCreate, db: session = Depends(get_db)):

    is_user = db.query(models.SystemUser).filter(models.SystemUser.user_id == request.user_id).first()

    if not is_user:
        raise HTTPException(status_code=404, detail="Invalid user id")

    new_patient = models.Patient(
        name=request.name,
        cnic=request.cnic,
        phone_no=request.phone_no,
        gender=request.gender,
        date_of_birth=request.date_of_birth,
        user_id=request.user_id
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return new_patient

@app.get("/get_all_patients", response_model=list[schemas.PatientDisplay], status_code=status.HTTP_200_OK, tags=["Patients"])
def get_all_patients(db: session = Depends(get_db)):
    return db.query(models.Patient).all()

@app.get("/get_patient/{p_id}", response_model=schemas.PatientDisplay, status_code=status.HTTP_200_OK, tags=["Patients"])
def get_single_patient(p_id: int, db: session = Depends(get_db)):
    patient = db.query(models.Patient).filter(models.Patient.p_id == p_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient



@app.post("/create_policy", status_code=status.HTTP_201_CREATED, tags=["Insurance_Policies"])
def create_policy(request: schemas.PolicyCreate, db: session = Depends(get_db)):

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
        status=request.status,
    )
    db.add(new_policy)
    db.commit()
    db.refresh(new_policy)
    return new_policy

@app.get("/single_policy{policy_id}", status_code=200, response_model=schemas.PolicyCreate, tags=["Insurance_Policies"])
def get_policy(policy_id : int , db: session = Depends(get_db)):
    policy =  db.query(models.InsurancePolicy).filter(models.InsurancePolicy.policy_id == policy_id).first()
        
    if not policy:    
        raise HTTPException(status_code=404, detail="Insurance Policy ID not found")
    return policy

@app.post("/submit_claim", response_model=schemas.PatientClaimDisplay, status_code=status.HTTP_201_CREATED, tags=["Claims"])
def submit_claim(request: schemas.PatientClaimCreate, db: session = Depends(get_db)):
    
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

@app.get("/get_all_claims", response_model=list[schemas.AllClaims], status_code=status.HTTP_200_OK, tags=["Claims"])
def get_all_pending_claims(db: session = Depends(get_db)):
    all_claims = db.query(models.PatientClaim).filter(models.PatientClaim.claim_status == 'Pending').all()
    claims =[ 
        {
            "claim_id" : claim.claim_id,
            "name": claim.patient.name,
            "phone_no": claim.patient.phone_no,
            "created_at": claim.created_at
        }
        for claim in all_claims # called list comprehension. cleaner way
    ]

    return claims

@app.get("/get_single_claim{claim_id}", response_model=schemas.PatientClaimDisplay, status_code=status.HTTP_200_OK, tags=["Claims"])
def get_single_claims(claim_id : int, db: session = Depends(get_db)):
    claim =  db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()

    if not claim:
        raise HTTPException(status_code=404, detail="Claim ID not found")
    
    return claim

@app.put("/change_claim_status{claim_id}/{claim_status}", status_code=status.HTTP_202_ACCEPTED, tags=['Claims'])
def claim_status(claim_id : int, claim_status: str, db: session = Depends(get_db)):

    claim = db.query(models.PatientClaim).filter(models.PatientClaim.claim_id == claim_id).first()

    if not claim:
        raise HTTPException(status_code=404, detail="claim id not found")
    
    claim.claim_status = claim_status

    db.commit()
    db.refresh(claim)

    return {"message": f"status set to {claim_status}"}

@app.put("/lock_claim{claim_id}/by{user_id}", status_code=status.HTTP_202_ACCEPTED, tags=['Claims'])
def claim_lock(claim_id : int, user_id: int, db: session = Depends(get_db)):

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

@app.put("/unlock_claim{claim_id}/by{user_id}", status_code=status.HTTP_202_ACCEPTED, tags=['Claims'])
def claim_unlock(claim_id : int, user_id: int, db: session = Depends(get_db)):

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8003, reload=True)