from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Date, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Doctor(Base):
    __tablename__ = 'doctor'

    doctor_id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)
    specialization = Column(String(50), nullable=True)

    last_visit = Column(DateTime)
    about = Column(String(255), nullable=True)
    phone_no = Column(String(20), nullable=True)

    visiting_notes = relationship("VisitingNotes", back_populates="doctor")
    
class Patient(Base):
    __tablename__ = 'patient'

    mpi = Column(Integer, primary_key= True, index= True)

    nic = Column(String(15), unique=True, nullable= False)
    name = Column(String(100), nullable= False)
    phone_no = Column(String(100), nullable= True)
    gender = Column(String(10), nullable= False)
    date_of_birth = Column(Date, nullable= True)
    address = Column(String(255), nullable= True)

    visiting_notes = relationship("VisitingNotes", back_populates="patient")

class VisitingNotes(Base):
    __tablename__ = 'visiting_notes'

    note_id = Column(Integer, primary_key=True, index=True)

    mpi = Column(Integer,ForeignKey('patient.mpi'), nullable=False)
    doctor_id = Column(Integer, ForeignKey('doctor.doctor_id'), nullable=False)

    visit_date = Column(DateTime, default=datetime.now())
    note_title = Column(String(1000), nullable=True)
    patient_complaint = Column(String(255), nullable=True)
    dignosis = Column(String(255), nullable=True)
    note_details = Column(String(1000), nullable=True)
    total_bill = Column(Float, default=0, nullable=True)

    doctor = relationship("Doctor", back_populates="visiting_notes")
    patient = relationship("Patient", back_populates="visiting_notes")
    report = relationship("LabReport", back_populates="visiting_notes")


class LabReport(Base): 
    # add the lab results column here as well (description, bill amount, amount_status(paid or not paid) )
    __tablename__ = "lab_report"

    report_id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(Integer, ForeignKey('visiting_notes.note_id'), nullable=False)

    lab_name = Column(String(100), nullable=False)
    test_name = Column(String(100), nullable=False)
    test_status = Column(String(10), nullable=False, default="Pending") # Arrived, decline
    created_at = Column(DateTime, default=datetime.now())
    updated_at = Column(DateTime, default=datetime.now())

    visiting_notes = relationship("VisitingNotes", back_populates="report")

# to apply migrations

## alembic init migrations
## go to alembic/env.py
## set database path into alembic.ini
## import model and set target_metadata = model.base.metadata

## alembic upgrade head
## if you apply any chnages to model.py
## alembic revision --autogenerate -m "your message"
## alembic upgrade head
## alembic downgrade -1
