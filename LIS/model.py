from datetime import datetime

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

base = declarative_base()

class User(base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)

    user_name = Column(String(50), nullable=False)
    email = Column(String(50), nullable=False)
    password = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.now())

    test_result = relationship("LabResult", back_populates="user")

class Patient(base):
    __tablename__ = "patient"

    mpi = Column(Integer, primary_key=True, index=True, autoincrement=False)

    fname = Column(String(25), nullable=False)
    lname = Column(String(50), nullable=True)
    dob = Column(DateTime, nullable=True)
    gender = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.now())
    updated_at = Column(DateTime, default=datetime.now())

    test_bill = relationship("LabTestBilling", back_populates="patient")
    test_req = relationship("LabTestRequest", back_populates="patient")

class LabTestRequest(base):
    __tablename__ = "test_request"

    test_req_id = Column(Integer, primary_key=True, index=True)
    vid = Column(String(20), nullable=True)
    mpi = Column(Integer, ForeignKey("patient.mpi"), nullable=False) # every test req will have a patient assign to it

    test_name = Column(Text, nullable=False)
    status = Column(String(10), nullable=False, default='Pending') #Pending or Accepted or Declined or Completed
    created_at = Column(DateTime, default=datetime.now())

    locked_by = Column(Integer, ForeignKey('users.user_id'), nullable=True)
    locked_at = Column(DateTime, nullable=True)

    test_result = relationship("LabResult", back_populates="test_req")
    test_bill = relationship("LabTestBilling", back_populates="test_req")
    patient = relationship("Patient", back_populates="test_req")

class LabTestBilling(base):
    __tablename__ = "test_billing"

    bill_id = Column(Integer, primary_key=True, index=True)
    mpi = Column(Integer, ForeignKey("patient.mpi"), nullable=False)
    test_req_id = Column(Integer, ForeignKey("test_request.test_req_id"), nullable=False)
    vid = Column(String(20), nullable=False)

    bill_amount = Column(Float, nullable=False)
    payment_status = Column(String(10), nullable=False)# pending, accepted, rejected
    create_at = Column(DateTime, default=datetime.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.now(), nullable=False)

    patient = relationship("Patient", back_populates="test_bill")
    test_req = relationship("LabTestRequest", back_populates="test_bill")

class LabResult(base):
    __tablename__ = "test_result"

    result_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    test_req_id = Column(Integer, ForeignKey("test_request.test_req_id"), nullable=False)

    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now(), nullable=False)

    mini_test = relationship("MiniLabResult", back_populates="test_result")
    user = relationship("User", back_populates="test_result")
    test_req = relationship("LabTestRequest", back_populates="test_result")

class MiniLabResult(base):
    __tablename__ = "mini_test_result"

    mini_test_id = Column(Integer, primary_key=True, index= True)
    result_id = Column(Integer, ForeignKey("test_result.result_id"), nullable=False)

    mini_test_name = Column(String(100), nullable=False)
    normal_range = Column(String(20), nullable=False)
    unit = Column(String(20), nullable=False)
    result_value = Column(String(7), nullable=False)

    test_result = relationship("LabResult", back_populates="mini_test")

class LoincMaster(base):
    __tablename__ = "loinc_master"

    loinc_code       = Column(String(10),  primary_key=True, index=True)
    long_common_name = Column(Text, nullable=False)
    short_name       = Column(String(150), nullable=True) # short name is not always available so it will be just for frontend.
    component        = Column(String(200), nullable=True)  # what is being measured ("WBC, RBC, Glucose")
    system           = Column(String(100), nullable=True)  # The specimen from which the measurement is taken (Blood, Urine, etc.)
    
# create a table for the lab tests, where the laboutry have their own test codes,
# on that table. i will map the lab tests with the loinc master table's test names.
# this way, when the lab test orders comes, i will first check which lab test it is refering to
# and then I will know the range, units of that test, and also do we even do that test or not.
