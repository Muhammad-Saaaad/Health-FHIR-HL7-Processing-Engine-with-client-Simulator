from fastapi import APIRouter, status, HTTPException, Depends, Response, Request
from sqlalchemy.orm import Session

from database import get_db
import model
from rate_limiting import limiter

router = APIRouter(tags=["Doctors"])

@router.get("/all_doctors", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
def get_doctors(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        return db.query(model.Doctor).all()
    except Exception as exp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))