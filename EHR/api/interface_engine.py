from fastapi import APIRouter, Request, status

router = APIRouter(tags=['engine'])

@router.post("/hl7/push")
async def hl7_push(req: Request):
    response = await req.json()
    print(response)
    return {"message":"data recieved"}

@router.post('/hl7/push', status_code=status.HTTP_200_OK)
async def hl7_push(req: Request):
    response = await req.json()
    print(response)
    return {"message": "sucessfully got the data"}