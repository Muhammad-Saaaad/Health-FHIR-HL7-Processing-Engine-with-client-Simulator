from datetime import datetime
import re


from fastapi import APIRouter, status, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from database import get_db
import model

router = APIRouter(tags=['Engine'])


@router.post("/get/new-patient", status_code=status.HTTP_200_OK)
async def add_patient(req: Request, db: Session = Depends(get_db)):
    try:
        data = await req.json()
        _, path = hl7_extract_paths(segment=data.split('\n')[1])
        values = get_hl7_value_by_path(data, path)
        
        dt = datetime.strptime(values['PID-7'], "%Y%m%d")
        date = dt.strftime("%Y-%m-%d")

        gender = "male" if values['PID-8'] == "M" else "female"

        patient = model.Patient(
            mpi = values['PID-3'],
            fname = values['PID-5.1'] if 'PID-5.1' in values else values['PID-5'].split(' ')[0],
            lname = values['PID-5.2'] if 'PID-5.2' in values else values['PID-5'].split(' ')[1:].join(' ') if len(values['PID-5'].split(' ')) > 1 else '' ,
            dob = date,
            gender = gender
        )

        db.add(patient)
        db.commit()
        db.refresh(patient)

        return {"message": "Patient Added sucessfully"}

    except Exception as exp:
        raise HTTPException(str(exp))

def hl7_extract_paths(segment):
    paths = []

    # for segment in segments[1:]:
    fields = segment.split('|')
    segment_type = fields[0] # PID etc.
    for i , field in enumerate(fields[1:], start=1):
        if field == '':
            continue
        if '^' in field:
            components = field.split('^')
            for j, component in enumerate(components, start=1):
                if '&' in component:
                    subcomponents = component.split('&')
                    for k, subcomponent in enumerate(subcomponents, start=1):
                        path = f"{segment_type}-{i}.{j}.{k}"
                        paths.append(path)
                else:
                    path = f"{segment_type}-{i}.{j}"
                    paths.append(path)
        else:
            path = f"{segment_type}-{i}"
            paths.append(path)
    return (segment_type, paths)

def get_hl7_value_by_path(hl7_message, paths): 
    segments = hl7_message.split('\n')[1:]
    value = {}
    for segment in segments:
        for path in paths:
            sp_path = re.split(r"-|\.", path) # [PID, 5, 2, 1]
           
            fields = segment.split("|")

            if fields[0] == sp_path[0]:

                if "^" in fields[int(sp_path[1])]:
                    components = fields[int(sp_path[1])].split("^")
                    
                    if "&" in components[int(sp_path[2])-1]:
                        sub_components = components[int(sp_path[2])-1].split("&")
                        value[path] = sub_components[int(sp_path[3])-1]
                    else:
                        value[path] = components[int(sp_path[2])-1] 
                else:
                    value[path] = fields[int(sp_path[1])]
        
    return value