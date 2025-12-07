from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base

base = declarative_base()

class Doctor(base):
    __tablename__ = 'doctor'

    doctor_id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    password = Column(String(200), nullable=False)
    specialization = Column(String(50), nullable=True) 

    date_join = Column(DateTime, nullable=True)
    about = Column(String(255), nullable=True)
    phone_no = Column(String(20), nullable=True)
