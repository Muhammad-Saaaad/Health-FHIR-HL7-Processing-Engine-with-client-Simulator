from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Date, Numeric, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class SystemUser(Base):
    __tablename__ = "SystemUser"

    user_id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, index=True)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now(), nullable=False)
    
    policies_managed = relationship("InsurancePolicy", back_populates="manager")
    locked_claims = relationship("PatientClaim", back_populates="locked_by")

class Patient(Base):
    __tablename__ = "Patient"

    pid = Column(Integer, primary_key=True, index=True)
    mpi = Column(Integer, unique=True, index=True, nullable=True)
    
    name = Column(String(100), nullable=False)
    phone_no = Column(String(20), nullable=True)
    gender = Column(String(10), nullable=False)
    date_of_birth = Column(Date, nullable=False)

    policies = relationship("InsurancePolicy", back_populates="patient")
    claims = relationship("PatientClaim", back_populates="patient")

class InsurancePolicy(Base):
    __tablename__ = "Insurance_Policy"

    policy_id = Column(Integer, primary_key=True, index=True) 
    pid = Column(Integer, ForeignKey("Patient.pid"), nullable=False)
    
    u_id = Column(Integer, ForeignKey("SystemUser.user_id"), nullable=False) # check if the user exists or not
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


class PatientClaim(Base):
    __tablename__ = "Patient_Claim"

    claim_id = Column(Integer, primary_key=True, index=True) 
    policy_id = Column(Integer, ForeignKey("Insurance_Policy.policy_id"), nullable=False) 
    mpi = Column(Integer, ForeignKey("Patient.mpi"), nullable=False)

    service_name = Column(String(100), nullable=False)
    bill_amount = Column(Numeric(10, 2), nullable=False)
    provider_phone_no = Column(String(20), nullable=True)
    claim_status = Column(String(10), nullable=False, default="Pending") # pending, Accepted , Rejected
    created_at = Column(DateTime, default=datetime.now(), nullable=False)
    locked_by_user_id = Column(Integer, ForeignKey("SystemUser.user_id"), nullable=True)
    locked_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="claims")
    policy = relationship("InsurancePolicy", back_populates="claims")
    locked_by = relationship("SystemUser", back_populates="locked_claims")