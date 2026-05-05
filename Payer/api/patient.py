from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import patient_schema as schema
from rate_limiting import limiter

router = APIRouter(tags=["Patients"])
from .logging_config import get_logger

logger = get_logger('Payer.api.patient', logfile=r'logs\payer_api.log')

@router.post("/reg_patient",  status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute")  # Limit to 15 requests per minute per IP
def register_patient(data: schema.PatientCreate, request: Request, response: Response,  db: Session = Depends(get_db)):
    """
    Register a new patient in the Payer system and automatically create an insurance policy.

    **Request Body:**
    - `mpi` (int, optional): Patient's medical record number.
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
    logger.info(f"register_patient called: name={data.name} mpi={data.mpi} insurance_type={data.insurance_type}")
    # user_id 0 means that it is inserted by the engine. 
    if data.user_id != 0:
        is_user = db.query(models.SystemUser).filter(models.SystemUser.user_id == data.user_id).first()

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
            data.user_id = engine_user.user_id
        else:            
            data.user_id = is_engine_user.user_id
    
    if db.query(models.Patient).filter(
            models.Patient.phone_no == data.phone_no,                            
            models.Patient.date_of_birth == data.date_of_birth,
            models.Patient.name == data.name).first():
        logger.warning(f"register_patient: duplicate patient attempted: name={data.name} phone_no={data.phone_no}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This Patient already exists")

    try:
        new_patient = models.Patient(
            mpi = data.mpi if data.mpi else None,
            u_id=data.user_id,
            name=data.name,
            phone_no=data.phone_no,
            gender=data.gender,
            date_of_birth=data.date_of_birth,
        )
        db.add(new_patient)
        db.flush()
        db.refresh(new_patient)

        total_coverage = 0
        if data.insurance_type in ("Gold", "Golden", "golden", "gold"):
            total_coverage = 1000000
        elif data.insurance_type in ("Silver", "silver"):
            total_coverage = 500000
        elif data.insurance_type in ("Bronze", "bronze"):
            total_coverage = 200000

        logger.info(f"Total coverage for {data.insurance_type} is {total_coverage}")

        new_policy = models.InsurancePolicy(
            pid=new_patient.pid,
            u_id = new_patient.u_id,
            category_name=data.insurance_type,
            total_coverage=total_coverage,
            amount_used=0,
            status="Active"
        )
        db.add(new_policy)
        db.commit()
        db.refresh(new_policy)

        logger.info(f"New patient created with ID: {new_patient.pid} and policy ID: {new_policy.policy_id}")

        return {"message": "Added Sucessfully"}
    except Exception as e:
        db.rollback()
        logger.exception(f"register_patient failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/get_all_patients", response_model=list[schema.PatientDisplay], status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def get_all_patients(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all patients registered in the Payer system.

    **Query Parameters:** None

    **Response (200 OK):**
    Returns `list[schema.PatientDisplay]`. Each item includes:
    - `p_id` (int): Patient internal ID
    - `mpi` (int | null): Master patient index
    - `name` (str): Patient full name
    - `gender` (str | null)
    - `date_of_birth` (date | null)
    - `phone_no` (str | null)
    - `policy_number` (int | null): active policy ID

    **Note:**
    - Returns an empty list if no patients exist.
    - Only the first active policy per patient is included in `policy_number`.

    **Error Responses:**
    - `400 Bad Request`: Unexpected database error
    """
    logger.info("get_all_patients called")
    try:
        all_patients = db.query(models.Patient).all()
        patients = []
        for p in all_patients:
            pocliy_number = db.query(models.InsurancePolicy).filter(models.InsurancePolicy.pid == p.pid, models.InsurancePolicy.status == "Active").first()
            if not pocliy_number:
                continue
            
            patients.append(schema.PatientDisplay(
                p_id=p.pid,
                mpi=p.mpi,
                name=p.name,
                gender=p.gender,
                date_of_birth=p.date_of_birth,
                phone_no=p.phone_no,
                policy_number=pocliy_number.policy_id
            ))

        logger.info(f"get_all_patients returning {len(patients)} patients")
        return patients
    except Exception as e:
        logger.exception(f"get_all_patients failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/get_patient/{p_id}", response_model=schema.PatientPolicyDetails, status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def get_single_patient(p_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve detailed information about a specific patient including their insurance policies.

    **Path Parameters:**
    - `p_id` (int, required): The unique ID of the patient to retrieve.

    **Response (200 OK):**
        Returns `schema.PatientPolicyDetails` with:
        
        * `p_id` (int)
        
        * `mpi` (int | null)
        
        * `name` (str)
        
        * `Age` (str | null): serialized age derived from date of birth
        
        * `phone_no` (str | null)
        
        * `gender` (str | null)
        
        * `patient_policy` (dict) where each policy item has:
            
            * `policy_id` (int)
            
            * `policy_plan` (str)
            
            * `total_coverage` (float)
            
            * `amount_used` (float)
            
            * `status` (str)

    **Error Responses:**
    - `404 Not Found`: No patient exists with the given `p_id`
    """
    logger.info(f"get_single_patient called for p_id={p_id}")
    patient = db.query(models.Patient).filter(models.Patient.pid == p_id).first()
    if not patient:
        logger.error(f"get_single_patient: p_id={p_id} not found")
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient_policies = {}
    for policiy in patient.policies:
        if policiy.status == "Active":
            patient_policies = {
                "policy_id": policiy.policy_id,
                "policy_plan": policiy.category_name,
                "total_coverage": policiy.total_coverage,
                "amount_used" : policiy.amount_used,
                "status": policiy.status
                # "description": policiy.description
            }
            break
        
    output = {
        "p_id" : patient.pid,
        "mpi": patient.mpi,
        "name" : patient.name,
        "Age": patient.date_of_birth, # field serializer will convert date to age str.
        "phone_no": patient.phone_no,
        "gender": patient.gender,
        "patient_policy": patient_policies
    }

    return output
