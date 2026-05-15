from sqlalchemy import JSON, Column, Integer, String, ForeignKey, DateTime, Date, Numeric, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Insurance(Base):
    __tablename__ = 'insurance'

    insurance_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False) # add unique here.

    __table_args__ = (
        UniqueConstraint('name', name='uq_insurance_name'),
    )

    user = relationship("SystemUser", back_populates="insurance")
    patient = relationship("Patient", back_populates="insurance")
    insurance_policy = relationship("InsurancePolicy", back_populates="insurance")

class Config(Base):          # we can extract the operation heading, url, hospital name via endpooint, where we can define that which hospital belong to which endpoint. 
    __tablename__ = "config"

    config_id = Column(Integer, primary_key=True, index=True)
    data = Column(JSON, nullable=False, default=list) # e.g.: [{"endpoint1": [{data1}, {data2}]} , {"endpoint2": [{data1}, {data2}]} ]
    history = Column(JSON, nullable=False, default=dict) # e.g: {"Hospital A": {"add-patient": 10, "add-visit": 20}, "Hospital B": {"add-patient": 5, "submit-claim": 15}}
    hold_flag = Column(Boolean, default=False)
    sent_to_engine = Column(Boolean, default=False) # this is for the engine to know that this config is already sent to engine or not. if sent then it will not send again to engine.

class SystemUser(Base):
    __tablename__ = "SystemUser"

    user_id = Column(Integer, primary_key=True, index=True)
    insurance_id = Column(String(50), ForeignKey('insurance.insurance_id', name='fk_system_user_insurance_id'), nullable=True) # insurance(fk of insurance)

    user_name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, index=True)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now(), nullable=False)
    roll = Column(Integer, default=1, nullable=False) # 1=user or 2=Admin

    __table_args__ = (
        UniqueConstraint('email', 'insurance_id', name='uq_email_insurance'),
    )
    
    patient = relationship("Patient", back_populates="user")
    policies_managed = relationship("InsurancePolicy", back_populates="manager")
    locked_claims = relationship("PatientClaim", back_populates="locked_by")
    insurance = relationship("Insurance", back_populates="user")

class Patient(Base):
    __tablename__ = "Patient" # make sure at the backend that the nic should remain unique.

    pid = Column(Integer, primary_key=True, index=True)
    nic = Column(String(20), index=True, nullable=True)
    u_id = Column(Integer, ForeignKey("SystemUser.user_id"), nullable=False)
    insurance_id = Column(String(50), ForeignKey('insurance.insurance_id', name='fk_patient_insurance_id'), nullable=True) # insurance(fk of insurance)
    
    name = Column(String(100), nullable=False)
    phone_no = Column(String(20), nullable=True)
    gender = Column(String(10), nullable=False)
    date_of_birth = Column(Date, nullable=False)

    policies = relationship("InsurancePolicy", back_populates="patient")
    claims = relationship("PatientClaim", back_populates="patient")
    user = relationship("SystemUser", back_populates="patient")
    insurance = relationship("Insurance", back_populates="patient")

class InsurancePolicy(Base):
    __tablename__ = "Insurance_Policy"

    policy_id = Column(Integer, primary_key=True, index=True) 
    pid = Column(Integer, ForeignKey("Patient.pid"), nullable=False)
    insurance_id = Column(String(50), ForeignKey('insurance.insurance_id', name='fk_insurance_policy_insurance_id'), nullable=True) # insurance(fk of insurance)
    
    u_id = Column(Integer, ForeignKey("SystemUser.user_id"), nullable=False)
    category_name = Column(String(50), nullable=False)
    total_coverage = Column(Numeric(10, 2), nullable=False)
    amount_used = Column(Numeric(10, 2), nullable=True)
    # description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="Active") # status active or inactive
    created_at = Column(DateTime, default=datetime.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.now(), nullable=False)

    patient = relationship("Patient", back_populates="policies")
    manager = relationship("SystemUser", back_populates="policies_managed")
    claims = relationship("PatientClaim", back_populates="policy")
    insurance = relationship("Insurance", back_populates="insurance_policy")

class PatientClaim(Base):
    __tablename__ = "Patient_Claim"

    claim_id = Column(Integer, primary_key=True, index=True) 
    policy_id = Column(Integer, ForeignKey("Insurance_Policy.policy_id"), nullable=False) 
    pid = Column(Integer, ForeignKey("Patient.pid"), nullable=False)
    vid = Column(Integer, nullable=True) # its not for now, but for later, if lab send claim to payer directly.

    service_included = Column(Boolean, nullable=False, default=False)
    tests_included = Column(Boolean, nullable=False, default=False)

    bill_amount = Column(Numeric(10, 2), nullable=False)
    claim_status = Column(String(10), nullable=False, default="Pending") # pending, Approved , Rejected
    created_at = Column(DateTime, default=datetime.now(), nullable=False)
    locked_by_user_id = Column(Integer, ForeignKey("SystemUser.user_id"), nullable=True)
    locked_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="claims")
    policy = relationship("InsurancePolicy", back_populates="claims")
    locked_by = relationship("SystemUser", back_populates="locked_claims")
