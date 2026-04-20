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
    """
        Retrieve summary-level lab reports for a visit note.

        Input:
        - Path parameter:
            - `note_id` (str): Visit note identifier.
        - No request body.

        Returns:
        - `200 OK` with list[`LabReportBase`].
        - Each item includes:
            - `report_id` (int)
            - `test_name` (str)
            - `updated_at` (str | null, formatted datetime)
            - `test_status` (str | null)

        Potential errors:
        - `404 Not Found`: Visit note does not exist.
    """

    if db.get(model.VisitingNotes, note_id) is None:
        logger.warning(f"Visit note with ID {note_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Visit note with the given ID {note_id} not found.")

    lab_reports = db.query(model.LabReport).filter(model.LabReport.visit_id == note_id).all()
    return lab_reports

@router.get("/lab-results/{report_id}", response_model=LabResult)
@limiter.limit("30/minute")
def get_lab_results(report_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """
        Retrieve detailed result data for a single lab report.

        Input:
        - Path parameter:
            - `report_id` (int): Lab report identifier.
        - No request body.

        Returns:
        - `200 OK` with `LabResult` payload:
            - `report_id` (int)
            - `test_name` (str)
            - `description` (str | null)
            - `mini_test_results` (list[`LabMiniTestResult`] | null), where each mini test has:
                - `mini_test_id` (int)
                - `test_name` (str)
                - `normal_range` (str)
                - `result_value` (str)

        Potential errors:
        - `404 Not Found`: Lab report does not exist.
        - `400 Bad Request`: Any unexpected database/server exception.
    """
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