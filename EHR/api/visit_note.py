from uuid import uuid4
import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, status, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .engine_service import send_visit_note_to_engine
from schemas import visit_note_schema as schema
from schemas import lab_schema
from database import get_db
import model
from rate_limiting import limiter

router = APIRouter(tags=['Visit Note'])

logger = logging.getLogger("visit_note_logger")
logger.setLevel(logging.INFO)
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")
handler = RotatingFileHandler(r"logs/visit_note.log", maxBytes=5*1024*1024, backupCount=2) # 5 MB per file, keep 2 backups
handler.setFormatter(formater)
logger.addHandler(handler)

@router.post("/visit-note-add", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def add_visit_note(visit_note: schema.VisitNote ,request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Create a new visit note for a patient, including billing and optional lab test orders.

    **Request Body:**
    - `mpi` (int, required): Master Patient Index - the unique identifier of the patient.
    - `doctor_id` (int, required): ID of the doctor creating the visit note.
    - `note_title` (str, required): Short title or subject of the visit (e.g., "Routine Checkup").
    - `patient_complaint` (str, required): Description of the patient's presenting complaint.
    - `dignosis` (str, required): Doctor's diagnosis for the visit.
    - `note_details` (str, optional): Additional notes or details from the visit.
    - `bill_amount` (float, required): Total insurance/billing amount for this visit.
    - `lab_name` (str, optional): Name of the laboratory for ordered tests (required if test_names is provided).
    - `test_names`
        
        [{

            **loinc_code: str**
            
            **long_common_name: str**
            
            **short_name: str | None**
            
            **component: str | None**
            
            **system: str | None**

        }]
        
        : List of lab test to order for this visit.

    **Request Schema (`schema.VisitNote`) fields:**
    - `mpi` (int), `doctor_id` (int)
    - `note_title` (str), `patient_complaint` (str), `dignosis` (str), `note_details` (str)
    - `bill_amount` (float)
    - `lab_name` (str | null)
    - `test_names` (list[`lab_schema.LoincMaster`] | null)

    **Response (201 Created):**
    Returns a JSON message:
    - `message`: "data inserted sucessfully"

    **Side Effects:**
    - Automatically creates a `Bill` record for the visit with `bill_status = False` (unpaid).
    - If `test_names` is provided, creates corresponding `LabReport` records linked to this visit.
    - All operations are atomic; a rollback occurs if any step fails.

    **Error Responses:**
    - `400 Bad Request`: Bill creation failed internally, or any unexpected database error
    """
    try:
        logger.info(f"Received request to add visit note for patient MPI: {visit_note.mpi} by doctor ID: {visit_note.doctor_id}")
        new_bill = model.Bill(
            insurance_amount = visit_note.bill_amount,
            bill_status = False,
        )

        db.add(new_bill)
        db.flush()

        bill_id = new_bill.bill_id
        logger.info(f"Created bill with ID: {bill_id}")
        
        if not db.get(model.Patient, visit_note.mpi):
            logger.error(f"Invalid patient MPI provided: {visit_note.mpi}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid patient MPI")

        is_doctor = db.query(model.Doctor).filter(model.Doctor.doctor_id == visit_note.doctor_id).first()
        if not is_doctor:
            logger.error(f"Invalid doctor ID provided: {visit_note.doctor_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doctor ID")

        new_visit_note = model.VisitingNotes(
            mpi = visit_note.mpi,
            doctor_id = visit_note.doctor_id,
            bill_id = bill_id,

            note_title = visit_note.note_title,
            patient_complaint = visit_note.patient_complaint,
            dignosis = visit_note.dignosis, 
            note_details = visit_note.note_details,
        )
        db.add(new_visit_note)
        db.flush()

        logger.info("Visit note added to session, preparing FHIR message for synchronization")

        unique_id = str(uuid4())
        patient_visit = {
            "resourceType": "Bundle",
            "type": "message",
            "id": unique_id,
            "entry": [
                {
                    "resource": {
                        "resourceType": "Practitioner",
                        "id": unique_id,
                        "identifier" :[ {"value": str(is_doctor.doctor_id)} ],
                        "name": [{"text": is_doctor.name}],
                        "telecom": [{"value": str(is_doctor.phone_no)}],
                        "extension": [{
                            "valueString": is_doctor.about
                        }]
                    }
                },
                {
                    "resource": {
                        "resourceType": "PractitionerRole",
                        "id": unique_id,
                        "specialty": [ { "coding": [{"display": str(is_doctor.specialization)}] } ],
                        "practitioner": {"reference": f"Practitioner/{str(is_doctor.doctor_id)}"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": unique_id,
                        "identifier": [
                            {
                                "value": str(new_visit_note.note_id)  # Primary key from EHR - send to PHR
                            }
                        ],
                        "status": "in-progress",
                        "class": {
                            "code": "AMB"  # AMB=Ambulatory, IMP=Inpatient, EMER=Emergency, VR=Virtual
                        },
                        # 1. ENCOUNTER TITLE
                        "type": [
                            {
                                "text": new_visit_note.note_title
                            }
                        ],
                        # 2. PATIENT COMPLAINT
                        "reasonCode": [
                            {
                                "text": new_visit_note.patient_complaint
                            }
                        ],
                        # 3. DIAGNOSIS - display field shows the disease name (no separate Condition resource needed)
                        "diagnosis": [
                            {
                                "condition": {
                                    "display": new_visit_note.dignosis  # display shows the disease name
                                }
                            }
                        ],
                        "subject": {"reference": f"patient/{str(visit_note.mpi)}"}, # reference to the patient resource (with mpi = 32 in this case)
                        # 4. CONSULTATION NOTES
                        "extension": [{
                                "valueString": new_visit_note.note_details
                            }
                        ]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Invoice",
                        "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                        "status": "issued",
                        "subject": {"reference": f"patient/{str(visit_note.mpi)}"},
                        "participant": [{"actor": {"reference": f"Practitioner/{str(is_doctor.doctor_id)}" } }],
                        "totalNet": {"value": str(visit_note.bill_amount)} # "currency": "USD", this can also be added.
                    }
                }
            ]
        }

        if visit_note.test_names and visit_note.lab_name: # if both lab name and test are provided, then only process lab tests
            
            is_sucess, patient_visit = get_test_report(
                unique_id = unique_id,
                fhir_message = patient_visit,
                visit_id = new_visit_note.note_id,
                mpi = visit_note.mpi,
                lab_name = visit_note.lab_name,
                test_details = visit_note.test_names,
                db = db
            )
            if not is_sucess:
                logger.error("Failed to process lab test details for visit note")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to process lab test details")    
            logger.info("Lab test details processed successfully and added to FHIR message")
        
        logger.info(f"Final FHIR message for synchronization: {patient_visit}")

        # ----- Send the complete FHIR message to the engine for synchronization -----
        sucess_message = send_visit_note_to_engine(patient_visit)

        if sucess_message == "sucessfull":
            db.commit()
            db.refresh(new_visit_note)
            logger.info(f"Visit note with ID {new_visit_note.note_id} committed to database and synchronized with engine successfully")
        else:
            logger.error(f"Failed to synchronize visit note with engine: {sucess_message}")
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to synchronize with engine: {sucess_message}")
        return {"message": "data inserted sucessfully"}
        
    except Exception as exp:
        db.rollback()
        logger.error(f"Error occurred while adding visit note: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")

def get_test_report(
        unique_id: str,
        fhir_message: dict,
        visit_id: int,
        mpi: int,
        lab_name: str, 
        test_details: list[lab_schema.LoincMaster], 
        db: Session) -> tuple[bool , dict[str, str]]:
    """
        Here I take the lab tests, and check if they exisits in the loinc master table, if yes then I will
        add them to the database as well as in the fhir message.
    """

    logger.info(f"Processing lab test details for visit ID: {visit_id}, patient MPI: {mpi}, lab name: {lab_name}")

    lab_reports = []
    for test_detail in test_details:
        loinc_entry = db.query(model.LoincMaster).filter(model.LoincMaster.loinc_code == test_detail.loinc_code).first()
        if not loinc_entry:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"LOINC code {test_detail.loinc_code} not found for test: {test_detail.long_common_name}")
        
        loinc_entry = loinc_entry.to_dict()  # Convert SQLAlchemy model to dict for easier access

        lab_report = model.LabReport(
            visit_id=visit_id,
            loinc_code=test_detail.loinc_code,
            lab_name=lab_name,
            test_name=test_detail.display_name,
        )
        lab_reports.append(lab_report)
        fhir_message["entry"].append(
            {
                "resource": {
                    "resourceType": "ServiceRequest",
                    "id": unique_id,
                    "status": "active",
                    "intent": "order",
                    "code":{
                        "coding": [
                            {
                                "code": test_detail.loinc_code,
                                "display": test_detail.long_common_name
                            }
                        ]
                    },
                    "subject": {"reference": f"patient/{str(mpi)}"},
                    "performer": [{"identifier": {"value": "PRAC-001"}, "display": lab_name.strip()}] # for now it is set to this dummy data.
                }
            }
        )
    db.add_all(lab_reports)
    db.flush()
    return True, fhir_message


@router.get("/all-visit-notes{doc_id}/{pid}", response_model=list[schema.ViewBaseNote] ,status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def visit_note(doc_id: int, pid: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve all visit notes for a specific patient created by a specific doctor.

    **Path Parameters:**
    - `doc_id` (int, required): The unique ID of the doctor.
    - `pid` (int, required): The patient's MPI (Master Patient Index).

    **Response (200 OK):**
    Returns `list[schema.ViewBaseNote]` where each item contains:
    - `note_id` (int)
    - `mpi` (int)
    - `doctor_id` (int)
    - `visit_date` (datetime)
    - `note_title` (str | null)

    **Note:**
    - Returns an empty list if the doctor has no visit notes for the specified patient.

    **Error Responses:**
    - `404 Not Found`: Patient with given MPI (`pid`) does not exist
    - `404 Not Found`: Doctor with given `doc_id` does not exist
    - `400 Bad Request`: Unexpected database or server error
    """

    is_patient = db.query(model.Patient).filter(model.Patient.mpi == pid).first()

    if not is_patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient does not exists")
    
    is_doc = db.query(model.Doctor).filter(model.Doctor.doctor_id == doc_id).first()
    if not is_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor does not exists")

    try:
        notes = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.doctor_id ==doc_id, model.VisitingNotes.mpi == pid).all()
        return notes
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')

@router.get("/visit-note{note_id}", response_model=schema.ViewNote ,status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")  # Limit to 30 requests per minute per IP
def visit_note(note_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Retrieve a single visit note by its unique note ID.

    **Path Parameters:**
    - `note_id` (int, required): The unique identifier of the visit note to retrieve.

    **Response (200 OK):**
    Returns `schema.ViewNote` with:
    - `note_id` (int)
    - `mpi` (int)
    - `doctor_id` (int)
    - `bill_id` (int | null)
    - `note_title` (str | null)
    - `patient_complaint` (str | null)
    - `dignosis` (str | null)
    - `note_details` (str | null)
    - `bill_amount` (float | null)
    - `bill_status` (str)


    **Error Responses:**
    - `404 Not Found`: No visit note exists with the given `note_id`
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        note = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.note_id == note_id).first()
        if not note:
            logger.exception(f"Visit note with ID {note_id} not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note id not found")
        
        total_bill = note.bill.insurance_amount if note.bill else 0
        total_bill += note.lab_charges if note.lab_charges else 0

        output_data = schema.ViewNote(
            note_id = note.note_id,
            mpi = note.mpi,
            doctor_id = note.doctor_id,
            bill_id = note.bill_id,

            consultation_bill = note.bill.insurance_amount if note.bill else None,
            bill_status = "paid" if note.bill and note.bill.bill_status else "unpaid",
            lab_bill=note.lab_charges if note.lab_charges else 0,
            total_bill=total_bill,

            note_title = note.note_title,
            patient_complaint = note.patient_complaint,
            dignosis = note.dignosis,
            note_details = note.note_details
        )
        return output_data
    except Exception as e:
        logger.exception(f"Error occurred while retrieving visit note with ID {note_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')