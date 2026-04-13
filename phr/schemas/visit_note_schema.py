from datetime import datetime

from pydantic import BaseModel, field_serializer

class VisitNoteBase(BaseModel):
    note_id: int
    visit_date: datetime
    note_title: str | None = None


    # Runs when returning response data so clients see "Month DD, YYYY".
    # NO @classmethod here because serializers run on ALREADY-CREATED objects during output conversion.
    # Pydantic passes self (the actual instance with real data) so we can read self.last_visit and format it.
    @field_serializer("visit_date")
    def format_visit_date(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M %p") # %p is for AM or PM. or you do .lower() for am or pm.

    model_config = {"from_attributes": True}

    model_config = {"from_attributes": True}

class VisitNoteDetail(BaseModel):
    note_id: int
    note_title: str | None = None
    patient_complaint: str | None = None
    diagnosis: str | None = None
    note_details: str | None = None
    consultation_bill: float | None = None
    payment_status: str | None = None

    lab_name: str | None = None
    lab_tests: list[str] | None = None
    test_bill: float | None = None # total amount of all lab tests

    model_config = {"from_attributes": True}