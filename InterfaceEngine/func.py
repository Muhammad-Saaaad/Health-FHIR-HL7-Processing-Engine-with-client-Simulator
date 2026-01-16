

# doctor add visitng note

#         patient = db.get(model.Patient, new_visit_note.patient_id)
#         doctor = db.get(model.Doctor, new_visit_note.doctor_id)

#         payload = send_bill(patient, doctor, new_visit_note, new_bill)
#         print("after send bill")

#          # as the new_visit_note is a object not a python data type
#         # so httpx won't accept it
#         # payload = jsonable_encoder(bill_fhir)
#         payload['destination'] = "Payer"

#         response = httpx.post("http://127.0.0.1:9000/fhir/ehr/push", json=payload)
#         if response.status_code == 200:
#         else:
#             db.rollback()
#             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payment not sent")
