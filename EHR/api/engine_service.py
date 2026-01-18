import httpx

async def register_engine(payload: dict):
    try:
        payload['source'] = 'EHR'
        payload['destination'] = ['LIS', 'Payer']
        response = httpx.post("http://127.0.0.1:9000/fhir/push", json=payload)
        
        if response.status_code == 200:
            return True
        return False
        
    except Exception as exp:
        return str(exp)