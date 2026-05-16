from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, String, Integer, ForeignKey, DateTime, Float, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

base = declarative_base()

class Lab(base):
    __tablename__ = 'lab'

    lab_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False) # add unique here.

    __table_args__ = (
        UniqueConstraint('name', name='uq_lab_name'),
    )

    user = relationship("User", back_populates="lab")
    patient = relationship("Patient", back_populates="lab")
    test_request = relationship("LabTestRequest", back_populates="lab")
    
class Config(base):          # we can extract the operation heading, url, hospital name via endpooint, where we can define that which hospital belong to which endpoint. 
    __tablename__ = "config"

    config_id = Column(Integer, primary_key=True, index=True)
    data = Column(JSON, nullable=False, default=list) # e.g.: [{"endpoint1": [{data1}, {data2}]} , {"endpoint2": [{data1}, {data2}]} ]
    history = Column(JSON, nullable=False, default=dict) # e.g: {"Hospital A": {"add-patient": 10, "add-visit": 20}, "Hospital B": {"add-patient": 5, "submit-claim": 15}}
    hold_flag = Column(Boolean, default=False)
    sent_to_engine = Column(Boolean, default=False) # this is for the engine to know that this config is already sent to engine or not. if sent then it will not send again to engine.

class User(base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(String(50), ForeignKey('lab.lab_id', name='fk_users_lab_id'), nullable=True) # lab(fk of lab)

    user_name = Column(String(50), nullable=True)
    email = Column(String(50), nullable=False)
    password = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    roll = Column(Integer, default=1, nullable=False) # 1=user or 2=Admin

    test_result = relationship("LabResult", back_populates="user")
    lab = relationship("Lab", back_populates="user")
    
    __table_args__ = (
        UniqueConstraint('email', 'lab_id', name='uq_email_lab'),
    )

class Patient(base):
    __tablename__ = "patient"

    nic = Column(String(20), primary_key=True, index=True)
    lab_id = Column(String(50), ForeignKey('lab.lab_id', name='fk_patient_lab_id'), nullable=False) # lab(fk of lab)

    fname = Column(String(25), nullable=False)
    lname = Column(String(50), nullable=True)
    dob = Column(DateTime, nullable=True)
    gender = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('lab_id', 'nic', name='uq_lab_nic'),
    )
    
    test_bill = relationship("LabTestBilling", back_populates="patient")
    test_req = relationship("LabTestRequest", back_populates="patient")
    lab = relationship("Lab", back_populates="patient")


class LabTestRequest(base):
    __tablename__ = "test_request"

    test_req_id = Column(Integer, primary_key=True, index=True)
    vid = Column(String(20), nullable=True)
    nic = Column(String(20), ForeignKey("patient.nic", name="fk_testreq_patient_nic"), nullable=False) # every test req will have a patient assign to it
    lab_id = Column(String(50), ForeignKey('lab.lab_id', name='fk_testreq_lab_id'), nullable=False) # lab(fk of lab)

    # add test code here.
    test_name = Column(Text, nullable=False)
    status = Column(String(10), nullable=False, default='Pending') #Pending or Accepted or Declined or Completed
    created_at = Column(DateTime, default=datetime.now)

    locked_by = Column(Integer, ForeignKey('users.user_id', name='fk_testreq_locked_by_user_id'), nullable=True)
    locked_at = Column(DateTime, nullable=True)

    test_result = relationship("LabResult", back_populates="test_req")
    test_bill = relationship("LabTestBilling", back_populates="test_req")
    patient = relationship("Patient", back_populates="test_req")
    lab = relationship("Lab", back_populates="test_request")

class LabTestBilling(base):
    __tablename__ = "test_billing"

    bill_id = Column(Integer, primary_key=True, index=True)
    nic = Column(String(20), ForeignKey("patient.nic", name="fk_test_billing_patient_nic"), nullable=False)
    test_req_id = Column(Integer, ForeignKey("test_request.test_req_id", name="fk_test_billing_test_req_id"), nullable=False)
    vid = Column(String(20), nullable=False)

    bill_amount = Column(Float, nullable=False)
    payment_status = Column(String(10), nullable=False) # pending, accepted, rejected
    create_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, nullable=False)

    patient = relationship("Patient", back_populates="test_bill")
    test_req = relationship("LabTestRequest", back_populates="test_bill")

class LabResult(base):
    __tablename__ = "test_result"

    result_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", name="fk_test_result_user_id"), nullable=False)
    test_req_id = Column(Integer, ForeignKey("test_request.test_req_id", name="fk_test_result_test_req_id"), nullable=False)

    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    mini_test = relationship("MiniLabResult", back_populates="test_result")
    user = relationship("User", back_populates="test_result")
    test_req = relationship("LabTestRequest", back_populates="test_result")

class MiniLabResult(base):
    __tablename__ = "mini_test_result"

    mini_test_id = Column(Integer, primary_key=True, index= True)
    result_id = Column(Integer, ForeignKey("test_result.result_id", name="fk_mini_test_result_result_id"), nullable=False)

    mini_test_name = Column(String(100), nullable=False)
    normal_range = Column(String(20), nullable=False)
    unit = Column(String(20), nullable=False)
    result_value = Column(String(7), nullable=False)

    test_result = relationship("LabResult", back_populates="mini_test")

class LabTest(base):

    __tablename__ = "lab_test"

    test_id = Column(Integer, primary_key=True, index=True)
    test_code = Column(String(30), nullable=False) # the code for the test from the lab
    
    test_name = Column(String(150), nullable=False) # the short name of the Loinc test
    parameter = Column(String(255), nullable=True) # the parameters for that test, which will be used to map with the loinc master table.
    unit = Column(String(30), nullable=True)
    gender = Column(String(10), nullable=True)
    adult_range = Column(String(20), nullable=True) # >= to 18 years
    child_range = Column(String(20), nullable=True) # < 18 years
