import logging
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from database import get_db
from rate_limiting import limiter
import model
from schemas.lab_schema import LabReportBase, LabResult

logger = logging.getLogger("phr_api_lab_report")
logger.setLevel(logging.INFO)   
handler = RotatingFileHandler(
    r"logs/lab_report.log", 
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=2
)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'))
logger.addHandler(handler)

router = APIRouter(tags=["Lab Reports"])

@router.get("/lab-reports-base/{note_id}", response_model=list[LabReportBase])
@limiter.limit("30/minute")
def get_lab_reports_base(note_id: str, request: Request, response: Response, db: Session = Depends(get_db)):

    if db.get(model.VisitingNotes, note_id) is None:
        logger.warning(f"Visit note with ID {note_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Visit note with the given ID {note_id} not found.")

    lab_reports = db.query(model.LabReport).filter(model.LabReport.visit_id == note_id).all()
    return lab_reports

@router.get("/lab-results/{report_id}", response_model=LabResult)
@limiter.limit("30/minute")
def get_lab_results(report_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        lab_report = db.get(model.LabReport, report_id)
        if lab_report is None:
            logger.warning(f"Lab report with ID {report_id} not found.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lab report with the given ID {report_id} not found.")
        
        response_data = {
            "report_id": lab_report.report_id,
            "test_name": lab_report.test_name,
            "description": lab_report.description,
            "mini_test_results": lab_report.mini_test
        }

        return response_data
    
    except Exception as exp:
        logger.error(f"Error fetching lab report details for report ID {report_id}: {str(exp)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exp))