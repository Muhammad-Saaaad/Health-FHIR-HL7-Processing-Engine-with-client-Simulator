import httpx

async def engine_push(payload: dict):
    try:
        payload['destination'] = "LIS,Payer"
        response = httpx.post("http://127.0.0.1:9000/", json=payload)
        
        if response.status_code == 200:
            return True
        return False
        
    except Exception as exp:
        return str(exp)