import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from fhir_validation import fhir_extract_paths, get_fhir_value_by_path

from database import get_db
import model

router = APIRouter(tags=["Engine-Service"])

logger = logging.getLogger("get_data")
logger.setLevel(logging.INFO)
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

if not logger.handlers:
    rotating_file_handler = RotatingFileHandler(
        r"logs\recieve_data.log",
        maxBytes=20000, # 20KB
        backupCount=1
    )
    rotating_file_handler.setFormatter(formater)
    logger.addHandler(rotating_file_handler)


@router.post("/add/patient", status_code=status.HTTP_200_OK)
async def add_patient(req: Request, db: Session = Depends(get_db)):
    """
    Ingest patient FHIR payload from InterfaceEngine and store in PHR database.

    **Response (200 OK):**
    Returns JSON object:
    - `message` (dict): extracted FHIR path-value map used for DB insertion.

    **Error Responses:**
    - `400 Bad Request`: Payload parsing, mapping, or database error.
    """
    try:
        json_data = await req.json()

        print(f"Recieved FHIR Data: {json_data}")
        logger.info(f"Recieved FHIR Data: {json_data}")

        resource_type = json_data['resourceType']
        db_data = {}
        if resource_type != "Bundle":

            paths = fhir_extract_paths(json_data)
            for path in paths:

                value = get_fhir_value_by_path(json_data, path)
                db_data[path] = value
                # print("path => ",path)
                # print("value => ",value)
        else: # if resource is Bundle

            for entry in json_data["entry"]:

                resource_type = entry['resource']['resourceType']
                paths = fhir_extract_paths(entry['resource'])
                for path in paths:

                    value = get_fhir_value_by_path(json_data, path)
                    db_data[path] = value
        
        nic = db_data.get("identifier[1].value", None)
        mpi = db_data.get("identifier[0].value", None)
        if mpi is None:
            logger.warning(f"Missing MPI in FHIR data: {json_data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing MPI in FHIR data: {json_data}")
        if nic is None:
            logger.warning(f"Missing NIC in FHIR data: {json_data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Missing NIC in FHIR data: {json_data}")
                    
        patient = model.Patient(
            nic = db_data["identifier[1].value"], # NIC
            mpi = db_data["identifier[0].value"], # MPI
            name = db_data["name[0].text"],
            gender = db_data["gender"],
            date_of_birth = db_data["birthDate"],
            address = db_data["address[0].text"],
            phone_no = db_data["telecom[0].value"]
        )
        db.add(patient)
        db.commit()

        logger.info(f"Patient added to DB with MPI: {patient.mpi}")
        return {"message": db_data}

    except Exception as e:
        logger.error(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/get-visit-note", status_code=status.HTTP_200_OK)
async def get_visit_note(req: Request, db: Session = Depends(get_db)):
    """
    Ingest visit-note bundle from InterfaceEngine and persist doctor, visit, and lab references.

    **Response (200 OK):**
    Returns JSON object with a `message` field. Typical success payload:
    - `{ "message": "Visit note and lab tests added to DB successfully" }`

    Other valid message payloads are returned for partial/validation scenarios
    (for example missing resource identifiers, duplicate visit note, or patient not found).

    **Error Responses:**
    - `400 Bad Request`: Invalid payload or processing error.
    """
    try:
        json_data = await req.json()

        print(f"Recieved FHIR Data: {json_data}")
        logger.info(f"Recieved FHIR Data: {json_data}")

        if json_data.get("resourceType") != "Bundle":
            logger.warning(f"Fhir data needs to be a Bundle resoruceType: \n{json_data}")
            return {"message": f"Fhir data needs to be a Bundle resoruceType: \n{json_data}" }
        
        doctor = {}
        visit_note = {}
        for index, indiviual_entry in enumerate(json_data['entry']):
            resource = indiviual_entry.get("resource", None)
            if not resource:

                logger.warning(f"No resource found in entry index : {index} \n {indiviual_entry}")
                continue

            if resource.get("resourceType") == "Practitioner":

                identifiers = resource.get("identifier", [])
                doctor_id = identifiers[0].get("value", None) if identifiers else None
                if not doctor_id:
                    logger.warning(f"No doctor id found in entry index : {index} \n {indiviual_entry}")
                    return {"message": f"No Practitioner id found \n {indiviual_entry}"}
                doctor["doctor_id"] = doctor_id

                names = resource.get("name", [])
                doctor_name = names[0].get("text", None) if names else None
                if not doctor_name:
                    logger.warning(f"No doctor name found in entry index : {index} \n {indiviual_entry}")
                doctor["name"] = doctor_name

                telecoms = resource.get("telecom", [])
                doctor['phone_no'] = telecoms[0].get("value", None) if telecoms else None
                
                extensions = resource.get("extension", [])
                doctor['about'] = extensions[0].get("valueString", None) if extensions else None

            elif resource.get("resourceType") == "PractitionerRole":
                specialties = resource.get("specialty", [])
                if specialties:
                    codings = specialties[0].get("coding", [])
                    doctor["specialization"] = codings[0].get("display", None) if codings else None
                else:
                    doctor["specialization"] = None
                
                hospital_name = resource.get("organization", {}).get("display", None)
                if hospital_name == None:
                    logger.warning(f"Hospital Name not Found in message: {indiviual_entry}")
                    return {"message": f"Hospital Name not Found in message: \n {indiviual_entry}"}

            elif resource.get("resourceType") == "Encounter":
                identifiers = resource.get("identifier", [])
                visit_note['note_id'] = identifiers[0].get("value", None) if identifiers else None

                if not visit_note['note_id']:
                    logger.warning(f"No visit note id found: \n {indiviual_entry}")
                    return {"message": f"No visit note id found: \n {indiviual_entry}"}

                mpi = resource.get("subject", {"reference": None}).get("reference", None)
                if not mpi:
                    logger.warning(f"No patient reference found in: \n {indiviual_entry}")
                    return {"message": f"No patient reference found \n {indiviual_entry}"}
                visit_note['mpi'] = mpi.split("/")[-1] # extract the mpi from the reference

                types = resource.get("type", [])
                visit_note['note_title'] = types[0].get("text", None) if types else None
                if not visit_note['note_title']:
                    logger.warning(f"No note title found in: \n {indiviual_entry}")

                reason_codes = resource.get("reasonCode", [])
                visit_note['patient_complaint'] = reason_codes[0].get("text", None) if reason_codes else None
                if not visit_note['patient_complaint']:
                    logger.warning(f"No patient complaint found in: \n {indiviual_entry}")

                diagnoses = resource.get("diagnosis", [])
                if diagnoses:
                    condition = diagnoses[0].get("condition", {})
                    visit_note['diagnosis'] = condition.get("display", None) if condition else None
                else:
                    visit_note['diagnosis'] = None
                if not visit_note['diagnosis']:
                    logger.warning(f"No diagnosis found in: \n {indiviual_entry}")

                extensions = resource.get("extension", [])
                visit_note['note_details'] = extensions[0].get("valueString", None) if extensions else None

                
        if not visit_note.get("note_id", None):
            logger.warning(f"No visit note id found in the entire bundle: \n {json_data}")
            return {"message": f"No visit note id found in the entire bundle: \n {json_data}"}
        
        if not doctor.get("doctor_id", None):
            logger.warning(f"No doctor id found in the entire bundle: \n {json_data}")
            return {"message": f"No doctor id found in the entire bundle: \n {json_data}"}
        
        if not visit_note.get("mpi", None):
            logger.warning(f"No patient reference found in the entire bundle: \n {json_data}")
            return {"message": f"No patient reference found in the entire bundle: \n {json_data}"}


        lab_tests = []
        for lab_test in json_data.get("entry", []):
            resource = lab_test.get("resource", None)

            if resource and resource.get("resourceType") == "Invoice":
                mpi = resource.get("subject", {"reference": None}).get("reference", None)
                participants = resource.get("participant", [])
                participant = participants[0].get("actor", {"reference": None}).get("reference", None) if participants else None
                
                if not mpi:
                    logger.warning(f"No patient reference found in invoice resource: \n {lab_test}")
                    pass
                if not participant:
                    logger.warning(f"No participant reference found in invoice resource: \n {lab_test}")
                    pass

                consultation_bill = resource.get("totalNet", {"value": None}).get("value", None)
                if not consultation_bill:
                    logger.warning(f"No consultation bill found in invoice resource: \n {lab_test}")
                    visit_note['consultation_bill'] = 0
                else:
                    visit_note['consultation_bill'] = consultation_bill
                
                visit_note['invoice_status'] = resource.get("status", None)

            if resource and resource.get("resourceType") == "ServiceRequest":
                # skipping the status, intent, lab name, and lab bill of the service request.
                code = resource.get("code", {})
                codings = code.get("coding", []) if code else []
                test_code = codings[0].get("code", None) if codings else None
                test_name = codings[0].get("display", None) if codings else None
                
                if not test_code or not test_name:
                    logger.warning(f"No test code or name found in: \n {lab_test}")
                    continue

                lab_mpi = resource.get("subject", {"reference": None}).get("reference", None)
                if lab_mpi and lab_mpi.split("/")[-1] != visit_note['mpi']:
                    logger.warning(f"Patient reference in lab test does not match with the patient reference in visit note: \n {lab_test}")
                    continue
                performers = resource.get("performer", [])
                lab_id = None
                lab_name = None
                if performers:
                    lab_id = performers[0].get("identifier", {"value": None}).get("value", None)
                    lab_name = performers[0].get("display", None)

                test_payload = {
                    "lab_id": lab_id,
                    "visit_id": visit_note['note_id'],
                    "lab_name": lab_name or "Unknown Lab",
                    "test_code": test_code,
                    "test_name": test_name
                }
                lab_tests.append(test_payload)
        
        logger.info(f"Extracted Doctor Data: {doctor}")
        logger.info(f"Extracted Visit Note Data: {visit_note}")
        logger.info(f"Extracted Lab Tests Data: {lab_tests}")

        patient = db.query(model.Patient).filter(model.Patient.mpi == visit_note['mpi']).first()
        if not patient:
            logger.warning(f"No patient found with MPI in database: {visit_note['mpi']}")
            return {"message": f"No patient found with MPI in database: {visit_note['mpi']}"}
        
        is_doctor = db.query(model.Doctor).filter(model.Doctor.doctor_id == doctor['doctor_id']).first()
        # if doctor is not avaiable then add the doctor else update the doctor information.
        if not is_doctor:
            doctor_obj = model.Doctor(
                doctor_id = doctor['doctor_id'],
                name = doctor['name'],
                specialization = doctor['specialization'],
                phone_no = doctor['phone_no'],
                about = doctor['about'],
            )
            db.add(doctor_obj)
        else:
            is_doctor.name = doctor['name']
            is_doctor.specialization = doctor['specialization']
            is_doctor.phone_no = doctor['phone_no']
            is_doctor.about = doctor['about']
            db.add(is_doctor)
        
        
        is_visit_note = db.query(model.VisitingNotes).filter(model.VisitingNotes.note_id == visit_note['note_id']).first()
        if is_visit_note:
            logger.warning(f"Visit note with the same id already exists in the database: {visit_note['note_id']}")
            return {"message": f"Visit note with the same id already exists in the database: {visit_note['note_id']}"}
        
        visit_note_obj = model.VisitingNotes(
            note_id = visit_note['note_id'],
            mpi = visit_note['mpi'],
            doctor_id = doctor['doctor_id'],
            note_title = visit_note.get('note_title', None),
            patient_complaint = visit_note.get('patient_complaint', None),
            diagnosis = visit_note.get('diagnosis', None),
            note_details = visit_note.get('note_details', None),
            consultation_bill = visit_note.get('consultation_bill', 0),
            # payment_status = visit_note.get('payment_status', "unpaid") if visit_note.get('payment_status', None) == 'issued' else "unpaid"
            payment_status = "unpaid" # By default, it is unpaid, but we can add logic to this later.
        )
        db.add(visit_note_obj)
        db.flush()

        for lab_test in lab_tests:
            if db.query(model.LabReport).filter(model.LabReport.test_code == lab_test['test_code'], model.LabReport.visit_id == lab_test['visit_id']).first():
                logger.warning(f"Lab test with the same code and the same visit id already exists in the lab report table")
                continue

            lab_report_obj = model.LabReport(
                visit_id = lab_test['visit_id'],
                lab_id = lab_test['lab_id'],
                lab_name = lab_test['lab_name'],
                test_code = lab_test['test_code'],
                test_name = lab_test['test_name'],
                description = None
            )
            db.add(lab_report_obj)
        db.commit()
        logger.info(f"Visit note and lab tests added to DB for patient MPI: {visit_note['mpi']}")
        return {"message": "Visit note and lab tests added to DB successfully"}

    except HTTPException as exp:
        db.rollback()
        logger.exception(f"HTTP Exception: {str(exp)}")
        raise exp
    except ValueError as exp:
        db.rollback()
        logger.exception(f"Invalid numeric identifier in payload: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid numeric identifier in payload")
    except Exception as e:
        db.rollback()
        logger.exception(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/receive-response-claim")
async def submit_claim_from_engine(req: Request, db: Session = Depends(get_db)):
    """
    Ingest patient FHIR payload from InterfaceEngine and store in PHR database.

    **Response (200 OK):**
    Returns JSON object:
    - `message` (dict): extracted FHIR path-value map used for DB insertion.

    **Error Responses:**
    - `400 Bad Request`: Payload parsing, mapping, or database error.
    """
    try:
        json_data = await req.json()

        logger.info(f"Recieved FHIR Data: {json_data}")

        resource_type = json_data['resourceType']
        db_data = {}
        if resource_type != "Bundle":

            paths = fhir_extract_paths(json_data)
            for path in paths:

                value = get_fhir_value_by_path(json_data, path)
                db_data[path] = value
        else: # if resource is Bundle
            for entry in json_data["entry"]:

                resource_type = entry['resource']['resourceType']
                paths = fhir_extract_paths(entry['resource'])
                for path in paths:

                    value = get_fhir_value_by_path(json_data, path)
                    db_data[path] = value

        patient_ref = db_data.get("patient.reference")
        if not patient_ref:
            logger.warning(f"Missing patient.reference in FHIR data: {json_data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing patient.reference in FHIR data")
        mpi = str(patient_ref.split("/")[-1]).strip()
        
        request_ref = db_data.get("request.reference")
        if not request_ref:
            logger.warning(f"Missing request.reference in FHIR data: {json_data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing request.reference in FHIR data")
        vid = str(request_ref.split("/")[-1]).strip()
        
        claim_status = db_data.get("status")
        if not claim_status:
            logger.warning(f"Missing status in FHIR data: {json_data}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing status in FHIR data")
        claim_status = str(claim_status).strip()
        logger.info(f"Extracted data for DB: MPI={mpi}, VID={vid}, Status={claim_status}")

        visit_note = db.query(model.VisitingNotes).filter(model.VisitingNotes.mpi == mpi, model.VisitingNotes.note_id == vid).first()
        if visit_note:
            visit_note.payment_status = str(claim_status).strip().capitalize()
            db.add(visit_note)
            db.commit()
            logger.info(f"Updated payment status to {visit_note.payment_status} for MPI={mpi}, VID={vid}")
            
            return {"message": f"Payment status updated to {visit_note.payment_status} for MPI={mpi}, VID={vid}"}
        else:
            logger.error(f"No visit note found for MPI={mpi}, VID={vid}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visit note found for MPI={mpi}, VID={vid}")

    except Exception as e:
        logger.error(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))