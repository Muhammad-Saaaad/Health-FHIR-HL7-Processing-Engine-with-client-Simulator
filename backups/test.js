arr = [1,2,3,4]

console.log(arr.map(item => item*2))

const jsonString = '{"name": "John", "age": 30}';
const obj = JSON.parse(jsonString);
console.log(obj.name); // Output: "John"


json_data = {
        "resourceType": "Bundle",
        "type": "message",
        "entry": [
            { 
                "resource": {
                    "resourceType": "Patient",
                    "identifier": [
                        { "type": { "coding": [{ "code": "MR" }]}, "value": "23" },
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
console.log(JSON.parse(JSON.stringify(json_data)));