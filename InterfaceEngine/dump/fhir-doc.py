def patient_to_fhir(patient):
    return{
        "resourceType": "Patient",
        "id": str(patient.patient_id),
        "identifier": [{"system": "CNIC", "value": patient.cnic}],
        "name": [{"text": patient.name}],
        "gender": patient.gender.lower(),
        "birthDate": patient.date_of_birth.strftime("%Y-%m-%d") if patient.date_of_birth else None,
        "telecom": [{"system": "phone", "value": patient.phone_no if patient.phone_no else None}],
        # "address": [{"text": patient.address}] if patient.address else None
    }

def doctor_to_fhir(doctor):
    return {
        "resourceType": "Practitioner",
        "id": str(doctor.doctor_id),
        "name": [{"text": doctor.name}],
        "telecom": [{"system": "phone", "value": doctor.phone_no}] if doctor.phone_no else None,
        "qualification": [{"code": doctor.specialization}] if doctor.specialization else None
    }

def visit_to_fhir(visit):
    return {
        "resourceType": "Encounter",
        "id": str(visit.note_id),
        "status": "finished", # note status, finished, in-progress
        # "class": {"code": "outpatient"},
        "subject": {"reference": f"Patient/{visit.patient_id}"},
        "participant": [{"individual": {"reference": f"Practitioner/{visit.doctor_id}"}}],
        "period": {"start": visit.visit_date.strftime("%Y-%m-%dT%H:%M:%S")}, # created at
        # "reasonCode": [{"text": visit.patient_complaint}],
        "diagnosis": [{"text": visit.dignosis}],
        # "note": [{"text": visit.note_details}]
    }

def bill_to_fhir(bill):
    return {
        "resourceType": "Claim",
        "id": str(bill.bill_id),
        "use": "claim",
        "created": bill.bill_date.strftime("%Y-%m-%dT%H:%M:%S"),
        "insurance": [{"value": bill.insurance_amount}],
        "status": "Pending"
    }

def lab_report_to_fhir(report):
    return {
        "resourceType": "DiagnosticReport",
        "id": str(report.report_id),
        "subject": {"reference": f"Patient/{report.visiting_notes.patient_id}"},
        "performer": [{"display": report.lab_name}],
        "code": {"text": report.test_name},
        "effectiveDateTime": report.test_date.strftime("%Y-%m-%dT%H:%M:%S")
    }

###

def send_bill(patient, doctor, visit_note, bill):
    patient_fhir = patient_to_fhir(patient)
    doctor_fhir = doctor_to_fhir(doctor)
    visit_note_fhir = visit_to_fhir(visit_note)
    bill_fhir = bill_to_fhir(bill)

    output = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": patient_fhir
            },
            {
                "resource": doctor_fhir,
            },
            {
                "resource": visit_note_fhir,
            },
            {
                "resource": bill_fhir,
            }
        ]
    }

    return output