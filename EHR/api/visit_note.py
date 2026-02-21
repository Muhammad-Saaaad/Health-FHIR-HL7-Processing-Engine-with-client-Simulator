from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas import visit_note_schema as schema
from database import get_db
import model

router = APIRouter(tags=['Visit Note'])

@router.post("/visit-note-add", status_code=status.HTTP_201_CREATED)
def add_visit_note(visit_note: schema.VisitNote ,db: Session = Depends(get_db)):
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
    - `test_names` (list[str], optional): List of lab test names to order for this visit.

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
        new_bill = model.Bill(
            insurance_amount = visit_note.bill_amount,
            bill_status = False,
        )

        db.add(new_bill)
        db.flush()

        bill_id = new_bill.bill_id
        if not db.get(model.Bill, bill_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bill not added due to internal issues")

        new_visit_note = model.VisitingNotes(
            mpi = visit_note.mpi,
            doctor_id = visit_note.doctor_id,
            bill_id = bill_id,

            note_title = visit_note.note_title,
            patient_complaint = visit_note.patient_complaint,
            dignosis = visit_note.dignosis, 
            note_details = visit_note.note_details
        )
        db.add(new_visit_note)
        db.flush()

        if visit_note.test_names:
            
            lab_models = []
            for test in visit_note.test_names:
                lab_models.append(
                    model.LabReport(
                        visit_id = new_visit_note.note_id,
                        lab_name = visit_note.lab_name,
                        test_name = test
                    )
                )
            db.add_all(lab_models)

        db.commit()
        db.refresh(new_visit_note)
        return JSONResponse(content={"message": "data inserted sucessfully"})
        
    except Exception as exp:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{str(exp)}")


@router.get("/all-visit-notes{doc_id}/{pid}", response_model=list[schema.ViewNote] ,status_code=status.HTTP_200_OK)
def visit_note(doc_id: int, pid: int, db: Session = Depends(get_db)):
    """
    Retrieve all visit notes for a specific patient created by a specific doctor.

    **Path Parameters:**
    - `doc_id` (int, required): The unique ID of the doctor.
    - `pid` (int, required): The patient's MPI (Master Patient Index).

    **Response (200 OK):**
    Returns a list of visit note objects matching both the doctor and patient. Each object includes
    the note details, diagnosis, complaints, and associated billing/lab information.

    **Note:**
    - Returns an empty list if the doctor has no visit notes for the specified patient.

    **Error Responses:**
    - `404 Not Found`: Patient with given MPI (`pid`) does not exist
    - `404 Not Found`: Doctor with given `doc_id` does not exist
    - `400 Bad Request`: Unexpected database or server error
    """
    try:

        is_patient = db.query(model.Patient).filter(model.Patient.mpi == pid).first()

        if not is_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient does not exists")
        
        is_doc = db.query(model.Doctor).filter(model.Doctor.doctor_id == doc_id).first()
        if not is_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor does not exists")

        notes = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.doctor_id ==doc_id, model.VisitingNotes.mpi == pid).all()
        return notes
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')

@router.get("/visit-note{note_id}", response_model=schema.ViewNote ,status_code=status.HTTP_200_OK)
def visit_note(note_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single visit note by its unique note ID.

    **Path Parameters:**
    - `note_id` (int, required): The unique identifier of the visit note to retrieve.

    **Response (200 OK):**
    Returns the full visit note object including note title, patient complaint, diagnosis,
    note details, and associated bill/lab report references.

    **Error Responses:**
    - `404 Not Found`: No visit note exists with the given `note_id`
    - `400 Bad Request`: Unexpected database or server error
    """
    try:
        notes = db.query(model.VisitingNotes) \
            .filter(model.VisitingNotes.note_id == note_id).first()
        if not notes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note id not found")
        return notes
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'{str(e)}')