from locust import HttpUser, task, between
import json


class InterfaceEngineUser(HttpUser):
    wait_time = between(1, 3)

    @task(1)
    def ingest_fhir_patient(self):
        """Test FHIR patient endpoint"""
        payload = {
            "resourceType": "Patient",
            "id": "1",
            "name": [{"use": "official", "family": "Doe", "given": ["John"]}],
            "gender": "male",
            "birthDate": "1980-01-01",
            "telecom": [{"system": "phone", "value": "555-1234"}],
            "address": [
                {
                    "use": "home",
                    "street": ["123 Main St"],
                    "city": "Springfield",
                    "state": "IL",
                    "postalCode": "62701",
                }
            ],
        }
        self.client.post("/patient-endpoint", json=payload)

    @task(1)
    def ingest_hl7_lab_result(self):
        """Test HL7 lab results endpoint"""
        hl7_message = """MSH|^~\\&|SendingApp|SendingFac|ReceivingApp|ReceivingFac|20240507120000||ORU^R01|MSG001|P|2.5
OBR|1|LAB001|LAB001-001|85025^Complete Blood Count||20240507||||||||||F
OBX|1|NM|WBC^White Blood Cell Count||7.5|K/uL|4.5-11.0|N|||F
OBX|2|NM|RBC^Red Blood Cell Count||4.8|M/uL|4.5-5.5|N|||F"""
        self.client.post("/lab-endpoint", data=hl7_message)

    @task(1)
    def health_check(self):
        """Health check endpoint"""
        self.client.get("/")
