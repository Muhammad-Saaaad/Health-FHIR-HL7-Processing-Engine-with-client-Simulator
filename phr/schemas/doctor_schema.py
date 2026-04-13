from datetime import date, datetime

from pydantic import BaseModel, field_serializer, field_validator

class DoctorBase(BaseModel):
    doctor_id: int
    name: str
    phone_no: str | None = None
    specialization: str | None = None
    last_visit: date

    # Runs before standard validation to accept incoming "YYYY-MM-DD" strings.
    # @classmethod is REQUIRED because validators run during object CREATION, before any instance exists.
    # Pydantic calls this method on the class itself (cls) to transform raw input before building the object.
    @field_validator("last_visit", mode="before")
    @classmethod
    def parse_last_visit(cls, value):
        if isinstance(value, str):
            # Convert API input text into a real date object.
            return datetime.strptime(value, "%Y-%m-%d").date()
        return value

    # Runs when returning response data so clients see "Month DD, YYYY".
    # NO @classmethod here because serializers run on ALREADY-CREATED objects during output conversion.
    # Pydantic passes self (the actual instance with real data) so we can read self.last_visit and format it.
    @field_serializer("last_visit")
    def format_last_visit(self, value: date) -> str:
        return value.strftime("%B %d, %Y")

    model_config = {"from_attributes": True}