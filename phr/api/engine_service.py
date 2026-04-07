import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from fhir_validation import fhir_extract_paths, get_fhir_value_by_path

from database import get_db
import model

router = APIRouter(tags=["Engine-Service"])

logger = logging.getLogger("get_data")
formater = logging.Formatter("%(asctime)s- %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")

if not logger.handlers:
    rotating_file_handler = RotatingFileHandler(
        r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\phr\logs\recieve_data.log",
        maxBytes=20000, # 20KB
        backupCount=1
    )
    rotating_file_handler.setFormatter(formater)
    logger.addHandler(rotating_file_handler)


@router.post("/add/patient", status_code=status.HTTP_200_OK)
async def add_patient(req: Request, db: Session = Depends(get_db)):
    
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

        logger.info("Patient added to DB with MPI: {patient.mpi}")
        return {"message": db_data}

    except Exception as e:
        logger.error(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/get-visit-note", status_code=status.HTTP_200_OK)
async def get_visit_note(req: Request, db: Session = Depends(get_db)):
    try:
        json_data = await req.json()

        print(f"Recieved FHIR Data: {json_data}")
        logger.info(f"Recieved FHIR Data: {json_data}")

        if json_data.get("resourceType") != "Bundle":
            logger.warning(f"Fhir data needs to be a Bundle resoruceType: \n{json_data}")
            return {"message": f"Fhir data needs to be a Bundle resoruceType: \n{json_data}" }
        
        doctor = {}
        visit_note = {}
        for index,indiviual_entry in enumerate(json_data['entry']):
            resource = indiviual_entry.get("resource", None)
            if not resource:

                logger.warning(f"No resource found in entry index : {index} \n {indiviual_entry}")
                continue

            if resource.get("resourceType") == "Practitioner":

                doctor_id = resource.get("identifier", [{"value": None}])[0].get("value", None)
                if not doctor_id:
                    logger.warning(f"No doctor id found in entry index : {index} \n {indiviual_entry}")
                    return {"message": f"No Practitioner id found \n {indiviual_entry}"}
                doctor["doctor_id"] = doctor_id

                doctor_name = resource.get("name", [{"text": None}])[0].get("text", None)
                if not doctor_name:
                    logger.warning(f"No doctor name found in entry index : {index} \n {indiviual_entry}")
                doctor["name"] = doctor_name

                doctor['phone_no'] = resource.get("telecom", [{"value": None}])[0].get("value", None)
                doctor['about'] = resource.get("extension", [{"valueString": None}])[0].get("valueString", None)

            elif resource.get("resourceType") == "PractitionerRole":
                doctor["specialization"] = resource.get("specialty", [{"coding": [{ "display": None }]}])[0].get("coding", [{ "display": None }])[0].get("display", None)

            elif resource.get("resourceType") == "Encounter":
                visit_note['note_id'] = resource.get("identifier", [ {"value": None} ])[0].get("value", None)

                if not visit_note['note_id']:
                    logger.warning(f"No visit note id found: \n {indiviual_entry}")
                    return {"message": f"No visit note id found: \n {indiviual_entry}"}
                visit_note['note_id'] = resource.get("identifier", [ {"value": None} ])[0].get("value", None)

                mpi = resource.get("subject", {"reference": None}).get("reference", None)
                if not mpi:
                    logger.warning(f"No patient reference found in: \n {indiviual_entry}")
                    return {"message": f"No patient reference found \n {indiviual_entry}"}
                visit_note['mpi'] = mpi.split("/")[-1] # extract the mpi from the reference

                note_title = resource.get("type", [{"text": None}])[0].get("text", None)
                if not note_title:
                    logger.warning(f"No note title found in: \n {indiviual_entry}")
                visit_note['note_title'] = note_title

                patient_complaint = resource.get("reasonCode", [{"text": None}])[0].get("text", None)
                if not patient_complaint:
                    logger.warning(f"No patient complaint found in: \n {indiviual_entry}")
                visit_note['patient_complaint'] = patient_complaint

                diagnosis = resource.get("diagnosis", [{"condition": {"display": None}}])[0].get("condition", {"display": None}).get("display", None)
                if not diagnosis:
                    logger.warning(f"No diagnosis found in: \n {indiviual_entry}")
                visit_note['diagnosis'] = diagnosis

                visit_note['note_details'] = resource.get("extension", [{"valueString": None}])[0].get("valueString", None)
                
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

            if resource and resource.get("resourceType") == "ServiceRequest":
                # skipping the status, intent, lab name, and lab bill of the service request.
                test_code = resource.get("code", {"coding": [{"code": None}]}).get("coding", [{"code": None}])[0].get("code", None)
                test_name = resource.get("code", {"coding": [{"display": None}]}).get("coding", [{"display": None}])[0].get("display", None)
                
                if not test_code or not test_name:
                    logger.warning(f"No test code or name found in: \n {lab_test}")
                    continue

                lab_mpi = resource.get("subject", {"reference": None}).get("reference", None)
                if lab_mpi.split("/")[-1] != visit_note['mpi']:
                    logger.warning(f"Patient reference in lab test does not match with the patient reference in visit note: \n {lab_test}")
                    continue
                lab_id = resource.get("performer", [{"reference": None}])[0].get("reference", None).split("/")[-1]
                lab_name = resource.get("performer", [{"display": None}])[0].get("display", None)

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
        if not is_doctor:
            doctor_obj = model.Doctor(
                doctor_id = doctor['doctor_id'],
                name = doctor['name'],
                specialization = doctor['specialization'],
                phone_no = doctor['phone_no'],
                about = doctor['about'],
            )
            db.add(doctor_obj)
            db.flush()
        
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
            note_details = visit_note.get('note_details', None)
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
                test_name = lab_test['test_name']
            )
            db.add(lab_report_obj)
        db.commit()
        logger.info(f"Visit note and lab tests added to DB for patient MPI: {visit_note['mpi']}")
        return {"message": "Visit note and lab tests added to DB successfully"}

    except HTTPException as exp:
        logger.exception(f"HTTP Exception: {str(exp)}")
        raise exp
    except ValueError as exp:
        logger.exception(f"Invalid numeric identifier in payload: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid numeric identifier in payload")
    except Exception as e:
        logger.exception(f"Error processing FHIR data: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))