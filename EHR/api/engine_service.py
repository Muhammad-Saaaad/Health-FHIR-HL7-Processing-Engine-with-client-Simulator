import httpx

def register_engine(data: dict):
    try:
        print("enter")
        response = httpx.post("http://127.0.0.1:9000/fhir/add-patient", json=data)
        if response.status_code == 200:
            return True
        return False
        
    except Exception as exp:
        print(str(exp))
        return str(exp)