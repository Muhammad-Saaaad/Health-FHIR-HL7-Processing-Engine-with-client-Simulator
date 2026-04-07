from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Date, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Doctor(Base):
    __tablename__ = 'doctor'

    doctor_id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(200), nullable=False)
    specialization = Column(String(50), nullable=True)

    date_join = Column(DateTime, default=datetime.now())
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
    date_of_birth = Column(Date, nullable= False)
    address = Column(String(255), nullable= True)
    # if we are dealing with multiple insurance providers, 
    # we can add insurance provider name and insurance number as well

    visiting_notes = relationship("VisitingNotes", back_populates="patient")

class Bill(Base):
    __tablename__ = 'bill'

    bill_id = Column(Integer, primary_key=True, index=True)

    insurance_amount = Column(Float, nullable=False) # service amount, lab amount(1000+2000 = 3000))
    bill_status = Column(Boolean, default=False) # true or false
    bill_date = Column(DateTime, default=datetime.now())

    visiting_notes = relationship("VisitingNotes", back_populates="bill")

class VisitingNotes(Base):
    __tablename__ = 'visiting_notes'

    note_id = Column(Integer, primary_key=True, index=True)

    mpi = Column(Integer,ForeignKey('patient.mpi'), nullable=False)
    doctor_id = Column(Integer, ForeignKey('doctor.doctor_id'), nullable=False)
    bill_id = Column(Integer, ForeignKey('bill.bill_id'), nullable=True)

    visit_date = Column(DateTime, default=datetime.now())
    note_title = Column(String(1000), nullable=True)
    patient_complaint = Column(String(255), nullable=True)
    dignosis = Column(String(255), nullable=True)
    note_details = Column(String(1000), nullable=True)
    lab_charges = Column(Float, nullable=True)

    doctor = relationship("Doctor", back_populates="visiting_notes")
    patient = relationship("Patient", back_populates="visiting_notes")
    bill = relationship("Bill", back_populates="visiting_notes")
    report = relationship("LabReport", back_populates="visiting_notes")

class LoincMaster(Base):
    __tablename__ = "loinc_master"

    loinc_code       = Column(String(10),  primary_key=True, index=True)
    long_common_name = Column(Text, nullable=False)
    short_name       = Column(String(150), nullable=True)
    component        = Column(String(200), nullable=True)  # what is being measured ("WBC, RBC, Glucose")
    system           = Column(String(100), nullable=True)  # The specimen from which the measurement is taken (Blood, Urine, etc.)
    

class LabReport(Base): 
    # add the lab results column here as well (description, bill amount, amount_status(paid or not paid) )
    __tablename__ = "lab_report"

    report_id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(Integer, ForeignKey('visiting_notes.note_id'), nullable=False)
    loinc_code = Column(String(10), ForeignKey('loinc_master.loinc_code'), nullable=False)

    lab_name = Column(String(100), nullable=False)
    test_name = Column(String(150), nullable=False) # the short name of the Loinc test
    description = Column(String(255), nullable=True) # added this for lab result description.
    test_status = Column(String(10), default="Pending") # Arrived, decline
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
