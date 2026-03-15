import os

from fastapi import FastAPI, status, HTTPException
from fastapi.responses import FileResponse

app = FastAPI(title="Send file")

@app.get("/download-file")
def download_file():
    path = r"E:\project\Health-FHIR-HL7-Processing-Engine-with-client-Simulator\test.py"

    if os.path.exists(path):
        print(path)
        return FileResponse(
            path=path,
            filename="test.py",
            media_type="text/x-python" # text/javascript # text/x-python # "text/markdown"
        )
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
    
@app.post("/check_json")
def check_json(json_dict: dict):
    try:

        data = json_dict["person"]
        return data
    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))
    
@app.post("/check_hl7")
def check_hl7(hl7_msg: str):
    try:

        data = hl7_msg["person"]
        return data
    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))