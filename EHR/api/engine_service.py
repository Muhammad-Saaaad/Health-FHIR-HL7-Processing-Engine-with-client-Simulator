import httpx

def register_engine(data: dict):
    try:
        data['source'] = 'EHR'
        data['destination'] = ['LIS', 'Payer']
        response = httpx.post("http://127.0.0.1:9000/fhir/push", json=data)
        
        if response.status_code == 200:
            return True
        return False
        
    except Exception as exp:
        return str(exp)