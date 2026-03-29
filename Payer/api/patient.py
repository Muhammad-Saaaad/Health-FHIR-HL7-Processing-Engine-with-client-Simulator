from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import patient_schema as schema
from rate_limiting import rate_limit

router = APIRouter(tags=["Patients"])

@router.post("/reg_patient",  status_code=status.HTTP_201_CREATED, tags=["Patients"])
@rate_limit(limit=15, period=60)  # Limit to 10 requests per minute per IP
def register_patient(request: schema.PatientCreate, db: Session = Depends(get_db)):
    """
    Register a new patient in the Payer system and automatically create an insurance policy.

    **Request Body:**
    - `name` (str, required): Patient's full name.
    - `phone_no` (str, optional): Patient's phone number. Must be unique across all patients.
    - `gender` (str, optional): Patient's gender (e.g., "Male", "Female").
    - `date_of_birth` (date, optional): Patient's date of birth in YYYY-MM-DD format.
    - `user_id` (int, required): ID of the system user creating this record. Must exist.
    - `insurance_type` (str, required): Insurance plan tier — one of `"Gold"`, `"Silver"`, or `"Bronze"`.

    **Side Effects:**
    - Automatically creates an `InsurancePolicy` record linked to the new patient with:
        - `Gold, Golden`  → total coverage of 1,000,000
        - `Silver` → total coverage of 500,000
        - `Bronze` → total coverage of 200,000

    **Response (201 Created):**
    Returns a confirmation message:
    - `message`: "Added Sucessfully"

    **Constraints:**
    - `user_id` must refer to an existing SystemUser.
    - `phone_no` must be unique — a duplicate phone number is rejected.

    **Error Responses:**
    - `404 Not Found`: `user_id` is not valid
    - `409 Conflict`: A patient with this phone number already exists
    - `500 Internal Server Error`: Database or unexpected error during creation
    - `422 Unprocessable Entity`: Invalid data format or missing required fields
    """
    # user_id 0 means that it is inserted by the engine. 
    if request.user_id != 0:
        is_user = db.query(models.SystemUser).filter(models.SystemUser.user_id == request.user_id).first()

        if not is_user:
            raise HTTPException(status_code=404, detail="Invalid user id")
    else:
        is_engine_user = db.query(models.SystemUser).filter(models.SystemUser.email == "engine@gmail.com").first()
        if not is_engine_user:
            engine_user = models.SystemUser(
                user_name="Engine",
                email="engine@gmail.com",
                password="1234"
            )
            db.add(engine_user)
            db.commit()
            db.refresh(engine_user)
            request.user_id = engine_user.user_id
        else:            
            request.user_id = is_engine_user.user_id
    
    if db.query(models.Patient).filter(
            models.Patient.phone_no == request.phone_no,                            
            models.Patient.date_of_birth == request.date_of_birth,
            models.Patient.name == request.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This Patient already exists")

    try:
        new_patient = models.Patient(
            u_id=request.user_id,
            name=request.name,
            phone_no=request.phone_no,
            gender=request.gender,
            date_of_birth=request.date_of_birth,
        )
        db.add(new_patient)
        db.flush()
        db.refresh(new_patient)

        total_coverage = 0
        if request.insurance_type in ("Gold", "Golden", "golden", "gold"):
            total_coverage = 1000000
        elif request.insurance_type in ("Silver", "silver"):
            total_coverage = 500000
        elif request.insurance_type in ("Bronze", "bronze"):
            total_coverage = 200000

        print(f"Total coverage for {request.insurance_type} is {total_coverage}")

        new_policy = models.InsurancePolicy(
            pid=new_patient.pid,
            u_id = new_patient.u_id,
            category_name=request.insurance_type,
            total_coverage=total_coverage,
            amount_used=0,
            status="active"
        )
        db.add(new_policy)
        db.commit()
        db.refresh(new_policy)

        print(f"New patient created with ID: {new_patient.pid} and policy ID: {new_policy.policy_id}")

        return {"message": "Added Sucessfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/get_all_patients", response_model=list[schema.PatientDisplay], status_code=status.HTTP_200_OK, tags=["Patients"])
@rate_limit(limit=30, period=60)  # Limit to 30 requests per minute per IP
def get_all_patients(db: Session = Depends(get_db)):
    """
    Retrieve all patients registered in the Payer system.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns a list of all patient records. Each item includes:
    - `p_id`: Patient's internal unique ID
    - `mpi`: Master Patient Index (linked from EHR)
    - `name`: Patient's full name
    - `gender`: Patient's gender
    - `date_of_birth`: Patient's date of birth
    - `phone_no`: Patient's phone number
    - `policy_number`: The ID of the patient's currently active insurance policy

    **Note:**
    - Returns an empty list if no patients exist.
    - Only the first active policy per patient is included in `policy_number`.

    **Error Responses:**
    - `400 Bad Request`: Unexpected database error
    """
    try:
        patients = [
            {
                "p_id": p.pid,
                "mpi": p.mpi,
                "name": p.name,
                "gender": p.gender,
                "date_of_birth": p.date_of_birth,
                "phone_no": p.phone_no,
                "policy_number": [policy.policy_id for policy in p.policies if policy.status == "active"][0]
            } for p in db.query(models.Patient).all()
        ]

        return patients
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/get_patient/{p_id}", response_model=schema.PatientPolicyDetails, status_code=status.HTTP_200_OK, tags=["Patients"])
@rate_limit(limit=30, period=60)
def get_single_patient(p_id: int, db: Session = Depends(get_db)):
    """
    Retrieve detailed information about a specific patient including their insurance policies.

    **Path Parameters:**
    - `p_id` (int, required): The unique ID of the patient to retrieve.

    **Response (200 OK):**
    Returns patient details with:
    - `p_id`: Patient's unique ID
    - `name`: Patient's full name
    - `cnic`: Patient's CNIC / national ID number
    - `date_of_birth`: Patient's date of birth
    - `patient_policy`: List of associated insurance policies, each containing:
        - `policy_id`: Policy's unique identifier
        - `category_name`: Insurance tier (e.g., \"Gold\", \"Silver\", \"Bronze\")
        - `total_coverage`: Maximum coverage amount
        - `amount_used`: Coverage already consumed
        - `description`: Additional policy notes

    **Error Responses:**
    - `404 Not Found`: No patient exists with the given `p_id`
    """
    patient = db.query(models.Patient).filter(models.Patient.p_id == p_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient_policies = []
    for policiy in patient.policies:
        patient_policies.append({
            "policy_id": policiy.policy_id,
            "category_name": policiy.category_name,
            "total_coverage": policiy.total_coverage,
            "amount_used" : policiy.amount_used,
            "description": policiy.description
        })
    output = {
        "p_id" : patient.p_id,
        "name" : patient.name,
        "cnic" : patient.cnic,
        "date_of_birth": patient.date_of_birth,

        "patient_policy": patient_policies
    }

    return output
