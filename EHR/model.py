from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

base = declarative_base()

class Doctor(base):
    __tablename__ = 'doctor'

    doctor_id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(200), nullable=False)
    specialization = Column(String(50), nullable=True) 

    date_join = Column(DateTime, nullable=True)
    about = Column(String(255), nullable=True)
    phone_no = Column(String(20), nullable=True)

    notifications = relationship("Notification", back_populates="doctor")
    visiting_notes = relationship("VisitingNotes", back_populates="doctor")

class Notification(base):
    __tablename__ = 'notification'

    notification_id = Column(Integer, primary_key=True, index=True)

    doctor_id = Column(Integer, ForeignKey('doctor.doctor_id'), nullable=False)
    title = Column(String(100), nullable=False)
    message = Column(String(255), nullable=False)
    is_read = Column(Boolean, default=False)

    doctor = relationship("Doctor", back_populates="notifications")

class Patient(base):
    __tablename__ = 'patient'

    patient_id = Column(Integer, primary_key= True, index= True)

    cnic = Column(String(15), nullable= False, unique= True)
    name = Column(String(100), nullable= False)
    phone_no = Column(String(100), nullable= True)
    gender = Column(String(10), nullable= False)
    date_of_birth = Column(DateTime, nullable= True)
    address = Column(String(255), nullable= True)

    visiting_notes = relationship("VisitingNotes", back_populates="patient")

class Bill(base):
    __tablename__ = 'bill'

    bill_id = Column(Integer, primary_key=True, index=True)

    insurance_amount = Column(Float, nullable=False)
    bill_status = Column(Boolean, default=False)
    bill_date = Column(DateTime, nullable=False)

    visiting_notes = relationship("VisitingNotes", back_populates="bill")

class VisitingNotes(base):
    __tablename__ = 'visiting_notes'

    note_id = Column(Integer, primary_key=True, index=True)

    patient_id = Column(Integer,ForeignKey('patient.patient_id'), nullable=False)
    doctor_id = Column(Integer, ForeignKey('doctor.doctor_id'), nullable=False)
    bill_id = Column(Integer, ForeignKey('bill.bill_id'), nullable=True)
    report_id = Column(Integer, ForeignKey('lab_report.report_id'), nullable=True)

    visit_date = Column(DateTime, nullable=False)
    note_title = Column(String(1000), nullable=True)
    patient_complaint = Column(String(255), nullable=True)
    dignosis = Column(String(255), nullable=True)
    note_details = Column(String(1000), nullable=True)

    doctor = relationship("Doctor", back_populates="visiting_notes")
    patient = relationship("Patient", back_populates="visiting_notes")
    bill = relationship("Bill", back_populates="visiting_notes")
    report = relationship("LabReport", back_populates="visiting_notes")


class LabReport(base):
    __tablename__ = "lab_report"

    report_id = Column(Integer, primary_key=True, index=True)

    lab_name = Column(String(100), nullable=False)
    test_name = Column(String(100), nullable=False)
    test_date = Column(DateTime, default=datetime.now(timezone.utc))

    visiting_notes = relationship("VisitingNotes", back_populates="report")

# to apply migrations

## alembic init alembic
## go to alembic/env.py
## set database path into alembic.ini
## import model and set target_metadata = model.base.metadata

## if you apply anychnages to model.py
## alembic revision --autogenerate -m "your message"
## alembic upgrade head
