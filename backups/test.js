arr = [1,2,3,4]

console.log(arr.map(item => item*2))

const jsonString = '{"name": "John", "age": 30}';
const obj = JSON.parse(jsonString);
console.log(obj.name); // Output: "John"


add_patient = { // ehr -> endpoint => /fhir/add-patient
        "resourceType": "Bundle",
        "type": "message",
        "entry": [
            { 
                "resource": {
                    "resourceType": "Patient",
                    "identifier": [
                        { "type": { "coding": [{ "code": "NI" }]}, "value": "37201-23123123"}
                    ],
                    "name": [{ "text": "Muhammad Saad" }],
                    "gender": "male",
                    "birthDate": "2004-10-06",
                    "address": [{ "text": "123 street, city, country" }],
                    "telecom" : [{
                        "value" : "+33 (237) 998327"
                    }]
                }
            },
            {
                "resource": {
                    "resourceType": "Coverage",
                    "identifier": [
                        {
                            "value": "3"
                        }   
                    ],
                    "status": "active",
                    "class": [
                        {
                            "type": { "coding": [{"code": "plan"}] },
                            "value": "Gold-Plan"
                        }
                    ],
                    "beneficiary": {
                        "reference": "23"
                    },
                    "subscriberId": "21",
                    "payor": [
                        {
                            "reference": "Organization/insurance-company-001"
                        }
                    ]
                }
            }
        ]
    }

add_patient ={ // phr -> endpoint => /add/patient
    "resourceType": "Patient",
    "identifier": [
        { "type": { "coding": [{ "code": "NI" }]}, "value": "37201-23123123"}
    ],
    "name": [{"text": "Muhammad Saad"}],
    "gender": "male",
    "birthDate": "2004-10-06",
    "address": [{ "text": "123 street, city, country" }],
    "telecom" : [{
        "value" : "+33 (237) 998327"
    }]
}

add_visit_note = { // ehr -> endpoint => /fhir/add-visit-note
        "resourceType": "Bundle",
        "type": "message",
        "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
        "entry": [
            {
                "resource": {
                    "resourceType": "Practitioner",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "identifier" :[ {"value": "PRAC-001"} ],
                    "name": [{"text": "Dr. Ayesha Khan"}],
                    "telecom": [{"value": "+33 (237) 998327"}],
                    "extension": [{
                        "valueString": "General Practitioner with 10 years of experience in primary care, specializing in patient-centered treatment and preventive medicine."
                    }]
                }
            },
            {
                "resource": {
                    "resourceType": "PractitionerRole",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "specialty": [ { "coding": [{"display": "General Practitioner"}] } ],
                    "practitioner": {"reference": "Practitioner/PRAC-001"},
                    "organization": {"display": "Shifa International"}
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "identifier": [
                        {
                            "value": "VID-2024-12345"
                        }
                    ],
                    "status": "in-progress",
                    "class": {
                        "code": "AMB"
                    },
                    "type": [
                        {
                            "text": "General Consultation"
                        }
                    ],
                    "reasonCode": [
                        {
                            "text": "Patient experiencing severe headache and dizziness"
                        }
                    ],
                    "diagnosis": [
                        {
                            "condition": {
                                "display": "Migraine"
                            }
                        }
                    ],
                    "subject": {"reference": "patient/37201-23123123"},
                    "extension": [{
                            "valueString": "Patient responded well to medication. Follow-up advised in 2 weeks."
                        }
                    ]
                }
            },
            {
                "resource": {
                    "resourceType": "Invoice",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "status": "issued",
                    "subject": {"reference": "Patient/37201-23123123"},
                    "participant": [{"actor": {"reference": "Practitioner/PRAC-001"}}],
                    "totalNet": {"value": "150.00"}
                }
            },
            {
                "resource": {
                    "resourceType": "ServiceRequest",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "status": "active",
                    "intent": "order",
                    "code":{
                        "coding": [
                            {
                                "code": "73761001",
                                "display": "Headache (disorder)"
                            }
                        ]
                    },
                    "subject": {"reference": "patient/37201-23123123"},
                    "performer": [{"identifier": {"value": "PRAC-001"}, "display": "IDC"}]
                }
            }
        ]
    }

add_visit_note = { // phr -> endpoint => /get-visit-note
        "resourceType": "Bundle",
        "type": "message",
        "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
        "entry": [
            {
                "resource": {
                    "resourceType": "Practitioner",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "identifier" :[ {"value": "PRAC-001"} ],
                    "name": [{"text": "Dr. Ayesha Khan"}],
                    "telecom": [{"value": "+33 (237) 998327"}],
                    "extension": [{
                        "valueString": "General Practitioner with 10 years of experience in primary care, specializing in patient-centered treatment and preventive medicine."
                    }]
                }
            },
            {
                "resource": {
                    "resourceType": "PractitionerRole",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "specialty": [ { "coding": [{"display": "General Practitioner"}] } ],
                    "practitioner": {"reference": "Practitioner/PRAC-001"},
                    "organization": {"display": "Shifa International"}
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "identifier": [
                        {
                            "value": "VID-2024-12345"
                        }
                    ],
                    "status": "in-progress",
                    "class": {
                        "code": "AMB"
                    },
                    "type": [
                        {
                            "text": "General Consultation"
                        }
                    ],
                    "reasonCode": [
                        {
                            "text": "Patient experiencing severe headache and dizziness"
                        }
                    ],
                    "diagnosis": [
                        {
                            "condition": {
                                "display": "Migraine"
                            }
                        }
                    ],
                    "subject": {"reference": "patient/37201-23123123"},
                    "extension": [{
                            "valueString": "Patient responded well to medication. Follow-up advised in 2 weeks."
                        }
                    ]
                }
            },
            {
                "resource": {
                    "resourceType": "Invoice",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "status": "issued",
                    "subject": {"reference": "Patient/37201-23123123"},
                    "participant": [{"actor": {"reference": "Practitioner/PRAC-001"}}],
                    "totalNet": {"value": "150.00"}
                }
            },
            {
                "resource": {
                    "resourceType": "ServiceRequest",
                    "id": "5e4d2222-11b8-4acc-9998-40a49e273c4e",
                    "status": "active",
                    "intent": "order",
                    "code":{
                        "coding": [
                            {
                                "code": "73761001",
                                "display": "Headache (disorder)"
                            }
                        ]
                    },
                    "subject": {"reference": "patient/37201-23123123"},
                    "performer": [{"identifier": {"value": "PRAC-001"}, "display": "IDC"}]
                }
            }
        ]
    }

submit_claim ={   // ehr => endpoint => /fhir/submit-claim
    "resourceType": "Claim",
        "id": "claim-example-01",
        "status": "active",
        "type": {
            "coding": [
                {
                    "display": "Service_LabTest"
                }   
            ]
        },
        "use": "claim",
        "patient": {
            "reference": "Patient/37201-23123123"
        },
        "created": "2026-02-03T12:00:00Z",
        "provider": {
            "reference":  "Encounter/123"
        },
        "priority": {
            "coding": [
                {
                    "code": "normal"
                }
            ]
        },
        "insurance": [
            {
                "sequence": 1,
                "focal": true,
                "coverage": {
                    "display": "Payer Health Insurance"
                }
            }
        ],
        "total": {
            "value": 150.00
        }
    }

response_claim = { // ehr => endpoint => /fhir/claim-response
        "resourceType": "ClaimResponse",
        "id": "res-123", 
        "status": "active",
        "type": { "coding": [{"code": "professional"}] },
        "use": "claim",
        "patient": {
            "reference": "patient/37201-23123123" 
        },
        "request": {
            "reference": "Encounter/123"
        },
        "created": "2026-05-02T13:23:15Z",
        "insurer": {
            "display": "Jubilee Insurance"
        },
        "outcome": "complete"
    }

send_response_claim = { // ehr => endpoint => /fhir/send-response-claim
    "resourceType": "ClaimResponse",
    "id": "res-123", 
    "status": "active",
    "type": { "coding": [{"code": "professional"}] },
    "use": "claim",
    "patient": {
        "reference": "patient/37201-23123123" 
    },
    "request": {
        "reference": "Encounter/123"
    },
    "created": "2026-05-02T13:23:15Z",
    "insurer": {
        "display": "Jubilee Insurance"
    },
    "outcome": "complete"
}

recieve_response_claim = { // phr => endpoint => /receive-response-claim
    "resourceType": "ClaimResponse",
    "id": "res-123", 
    "status": "active",
    "type": { "coding": [{"code": "professional"}] },
    "use": "claim",
    "patient": {
        "reference": "patient/37201-23123123" 
    },
    "request": {
        "reference": "Encounter/123"
    },
    "created": "2026-05-02T13:23:15Z",
    "insurer": {
        "display": "Jubilee Insurance"
    },
    "outcome": "complete"
}

add_patient = // LIS -> endpoint => /get/new-patient
MSH|^~\\&|EHR||LIS||20260203120000||ADT^A01|MSG00001|P|2.5
PID|1||37201-7687213-2||saad^Muhammad||20041006|M|||||+92-315-3726612

add_patient = // Payer -> endpoint => /get/registed_patient
MSH|^~\\&|EHR||payer||20260203120000||ADT^A01|MSG00001|P|2.5
PID|1||37201-7687213-2||saad^Muhammad||20041006|M|||||
IN1|||||||||||||||Silver|||||||||||||||||||||9||||||||||||||||

// -----------------------------------------------------------------------------------------------------------------------------------------


add_visit_note = // lis => endpoint -> /take_lab_order
MSH|^~\\&|EHR||LIS||20260203120000||ORM^O01|MSG00002|P|2.5
PID|1||37201-7687213-2|||||||||||
OBR|01|VID-01||2093-3^Total cholesterol|||||||||||


// ---------------------------------------------------------------------------------------------------------------------------------------------

submit_claim = // Payer => endpoint => /submit-claim
MSH|^~\\&|EHR||LIS||20260203120000||ADT^A01|MSG00001|P|2.5
PID|1||137201-7687213-2||
PV1|1||||||||||||||||||1231
FT1|1|||20260203120000|||Service_LabTest|150.00||||||||||||||||

response_claim = // Payer => endpoint => /send/claim_response
MSH|^~\\&|payer||EHR||20260502132315||ACK^P03|MSG00003|P|2.5
PID|1||137201-7687213-2||
PV1|1||||||||||||||||||1231
MSA|AA|MSG00003|ClaimAccepted