from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Date, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Doctor(Base):
    __tablename__ = 'doctor'

    doctor_id = Column(String(20), primary_key=True, index=True)

    name = Column(String(100), nullable=False)
    specialization = Column(String(50), nullable=True)

    last_visit = Column(Date, default=datetime.now().date())
    about = Column(String(255), nullable=True)
    phone_no = Column(String(20), nullable=True)

    visiting_notes = relationship("VisitingNotes", back_populates="doctor")
    
class Patient(Base):
    __tablename__ = 'patient'

    mpi = Column(String(20), primary_key= True, index= True)

    nic = Column(String(15), unique=True, nullable= False)
    password = Column(String(50), nullable= False, default="")
    name = Column(String(100), nullable= False)
    phone_no = Column(String(100), nullable= True)
    gender = Column(String(10), nullable= False)
    date_of_birth = Column(Date, nullable= True)
    address = Column(String(255), nullable= True)

    visiting_notes = relationship("VisitingNotes", back_populates="patient")

class VisitingNotes(Base):
    __tablename__ = 'visiting_notes'

    note_id = Column(String(20), primary_key=True, index=True)

    mpi = Column(String(20),ForeignKey('patient.mpi'), nullable=False)
    doctor_id = Column(String(20), ForeignKey('doctor.doctor_id'), nullable=False)

    visit_date = Column(DateTime, default=datetime.now())
    note_title = Column(Text, nullable=True)
    patient_complaint = Column(String(255), nullable=True)
    diagnosis = Column(String(255), nullable=True)
    note_details = Column(Text, nullable=True)
    consultation_bill = Column(Float, default=0, nullable=True)
    payment_status = Column(String(20), default="unpaid", nullable=True)

    doctor = relationship("Doctor", back_populates="visiting_notes")
    patient = relationship("Patient", back_populates="visiting_notes")
    report = relationship("LabReport", back_populates="visiting_notes")


class LabReport(Base): 
    # add the lab results column here as well (description, bill amount, amount_status(paid or not paid) )
    __tablename__ = "lab_report"

    report_id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(String(20), ForeignKey('visiting_notes.note_id'), nullable=False)
    lab_id = Column(String(20), nullable=False) # the id for the lab from which the test is done.

    lab_name = Column(String(100), nullable=False) # from which lab the test is done
    test_code = Column(String(30), nullable=False)
    test_name = Column(Text, nullable=False)
    test_bill = Column(Float, default=0, nullable=True)
    description = Column(String(255), nullable=True) # added this for lab result description.
    test_status = Column(String(10), default="Pending") # Completed, Pending, Cancelled
    created_at = Column(DateTime, default=datetime.now())
    updated_at = Column(DateTime, default=datetime.now())

    visiting_notes = relationship("VisitingNotes", back_populates="report")
    mini_test = relationship("MiniLabResult", back_populates="test_report")

class MiniLabResult(Base):
    __tablename__ = "mini_test_result"

    mini_test_id = Column(Integer, primary_key=True, index= True)
    report_id = Column(Integer, ForeignKey("lab_report.report_id"), nullable=False)

    test_name = Column(String(50), nullable=False)
    normal_range = Column(String(20), nullable=False)
    result_value = Column(String(7), nullable=False)

    test_report = relationship("LabReport", back_populates="mini_test")


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
