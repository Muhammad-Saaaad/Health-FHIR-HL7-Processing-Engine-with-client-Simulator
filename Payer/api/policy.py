from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session

from database import get_db
import models
from schemas import policy_schema as schema
from rate_limiting import limiter

router = APIRouter(tags=["Insurance_Policies"])
from .logging_config import get_logger

logger = get_logger('Payer.api.policy', logfile=r'logs\payer_api.log')

# this is already used with the patient registration endpoint, so we can skip it here
# @router.post("/create_policy", status_code=status.HTTP_201_CREATED, tags=["Insurance_Policies"])
# @limiter.limit(limit=20, period=60)  # Limit to 20 requests per minute per IP
# def create_policy(request: schema.PolicyCreate, db: Session = Depends(get_db)):
#     """
#     Create a new insurance policy and associate it with a patient.

#     **Request Body:**
#     - `p_id` (int, required): Valid patient ID to associate the policy with. Must exist in the system.
#     - `u_id` (int, required): Valid system user/admin ID creating the policy. Must exist in the system.
#     - `category_name` (str, required): Insurance category or plan name (e.g., "Premium", "Basic", "Gold").
#     - `total_coverage` (float, required): Maximum coverage amount allowed under this policy.
#     - `amount_used` (float, optional, default=0.0): Amount already consumed from the total coverage.
#     - `description` (str, optional): Additional notes or details about the policy.

#     **Response (201 Created):**
#     Returns the newly created policy object with all submitted fields plus:
#     - `policy_id`: Auto-generated unique policy identifier

#     **Constraints:**
#     - `p_id` must refer to an existing patient in the Patient table.
#     - `u_id` must refer to an existing user in the SystemUser table.

#     **Error Responses:**
#     - `404 Not Found`: Patient with given `p_id` does not exist
#     - `404 Not Found`: User with given `u_id` does not exist
#     - `422 Unprocessable Entity`: Invalid data format or missing required fields
#     """
#     if not db.query(models.Patient).filter(models.Patient.p_id == request.p_id).first():
#         raise HTTPException(status_code=404, detail="Patient ID not found")
    
#     is_user = db.query(models.SystemUser).filter(models.SystemUser.user_id == request.u_id).first()

#     if not is_user:
#         raise HTTPException(status_code=404, detail="Invalid user id")
        
#     new_policy = models.InsurancePolicy(
#         p_id=request.p_id,
#         u_id=request.u_id,
#         category_name=request.category_name,
#         total_coverage=request.total_coverage,
#         amount_used=request.amount_used,
#         description=request.description,
#     )
#     db.add(new_policy)
#     db.commit()
#     db.refresh(new_policy)
#     return new_policy

@router.get("/single_policy{policy_id}", status_code=200, tags=["Insurance_Policies"])
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def get_policy(policy_id : int , request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve the details of a specific insurance policy by its ID.

    **Path Parameters:**
    - `policy_id` (int, required): The unique identifier of the policy to retrieve.

    **Response (200 OK):**
    Returns the policy details including:
    - `policy_id`: Policy ID
    - `pid`: Associated patient's ID
    - `u_id`: ID of the user/admin who created the policy
    - `category_name`: Insurance plan/category name
    - `total_coverage`: Maximum coverage amount
    - `amount_used`: Amount already used from the coverage
    - `status`: Policy status (for example, `Active`)

    **Error Responses:**
    - `404 Not Found`: No policy exists with the given `policy_id`
    """
    logger.info(f"get_policy called for policy_id={policy_id}")
    policy =  db.query(models.InsurancePolicy).filter(models.InsurancePolicy.policy_id == policy_id).first()
        
    if not policy:
        logger.error(f"get_policy: policy_id={policy_id} not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insurance Policy ID not found")
    logger.info(f"get_policy found policy_id={policy_id}")
    return policy

@router.get("/all_patients_per_policy_category{policy_category}/{insurance_id}", status_code=200, tags=["Insurance_Policies"])
@limiter.limit("20/minute")  # Limit to 20 requests per minute per IP
def patients_per_policy_cat(policy_category : str, insurance_id: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all patients enrolled in a specific insurance policy category.

    **Path Parameters:**
    - `policy_category` (str, required): The policy category name to filter by (e.g., "Gold", "Silver", "Bronze").
    - `insurance_id` (str, required): The ID of the insurance company to filter by.

    **Response (200 OK):**
    Returns a list of patient objects enrolled in that category. Each item includes:
    - `pid`: Patient's unique ID
    - `name`: Patient's full name
    - `date_of_birth`: Patient's date of birth
    - `policy_category`: The category name used to filter

    **Note:**
    - Returns an empty list if no patients are enrolled in the specified category.
    - The category name match is case-sensitive (e.g., "Gold" vs "gold" are different).

    **Known Issue:**
    - The response dict currently includes `"cnic": d.cnic`, but the Payer `Patient` model
      has no `cnic` column. This will raise an `AttributeError` at runtime and needs to be removed.
    """
    logger.info(f"patients_per_policy_cat called for category={policy_category}")
    try:
        data = db.query(models.Patient).join(models.InsurancePolicy).filter(
            models.InsurancePolicy.category_name == policy_category,
            models.InsurancePolicy.insurance_id == insurance_id
        ).all()

        output = []
        for d in data:
            output.append({
                "pid": d.pid,
                "name": d.name,
                "date_of_birth": d.date_of_birth,
                "policy_category": policy_category
            })
        logger.info(f"patients_per_policy_cat returning {len(output)} patients for category={policy_category}")
        return output
    except Exception as e:
        logger.exception(f"patients_per_policy_cat failed for category={policy_category}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
