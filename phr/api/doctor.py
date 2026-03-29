from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import model
from rate_limiting import rate_limit

router = APIRouter(tags=["Doctors"])

@router.get("/all_doctors", status_code=status.HTTP_200_OK)
@rate_limit(limit=30, period=60)
def get_doctors(db: Session = Depends(get_db)):
    try:
        return db.query(model.Doctor).all()
    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))