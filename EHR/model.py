from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Date, Float, Text, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Hospital(Base):
    __tablename__ = 'hospital'

    hospital_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False) # add unique here.

    __table_args__ = (
        UniqueConstraint('name', name='uq_hospital_name'),
    )

    users = relationship("Users", back_populates="hospital")
    patient = relationship("Patient", back_populates="hospital")
    visiting_notes = relationship("VisitingNotes", back_populates="hospital")

class Config(Base):          # we can extract the operation heading, url, hospital name via endpooint, where we can define that which hospital belong to which endpoint. 
    __tablename__ = "config"

    config_id = Column(Integer, primary_key=True, index=True)
    data = Column(JSON, nullable=False, default=list) # e.g.: [{"endpoint1": [{data1}, {data2}]} , {"endpoint2": [{data1}, {data2}]} ]
    history = Column(JSON, nullable=False, default=dict) # e.g: {"Hospital A": {"add-patient": 10, "add-visit": 20}, "Hospital B": {"add-patient": 5, "submit-claim": 15}}
    hold_flag = Column(Boolean, default=False)
    sent_to_engine = Column(Boolean, default=False) # this is for the engine to know that this config is already sent to engine or not. if sent then it will not send again to engine.

class Users(Base):
    __tablename__ = 'users'

    users_id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(String(50), ForeignKey('hospital.hospital_id', name='fk_users_hospital_id'), nullable=True) # hospital(fk of hospital)

    name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=False)  # Removed unique=True - see __table_args__ for composite constraint
    password = Column(String(200), nullable=False)
    specialization = Column(String(50), nullable=True)
    roll = Column(Integer, default=1, nullable=False) # 1=Doctor or 2=Admin

    date_join = Column(DateTime, default=datetime.now())
    about = Column(String(255), nullable=True)
    phone_no = Column(String(20), nullable=True)

    visiting_notes = relationship("VisitingNotes", back_populates="user")
    hospital = relationship("Hospital", back_populates="users")
    
    # Constraint: Same email cannot exist with same hospital_id
    # But same email can exist in different hospitals, and hospital_id can be NULL
    __table_args__ = (
        UniqueConstraint('email', 'hospital_id', name='uq_email_hospital'),
    )
    
class Patient(Base):
    __tablename__ = 'patient'

    mpi = Column(Integer, primary_key= True, index= True)
    hospital_id = Column(String(50), ForeignKey('hospital.hospital_id', name="FK__patient__hospita__5E8A0973"),  nullable=False) # hospital(fk of hospital)

    nic = Column(String(20), nullable= False)
    name = Column(String(100), nullable= False)
    phone_no = Column(String(100), nullable= True)
    gender = Column(String(10), nullable= False)
    date_of_birth = Column(Date, nullable= False)
    address = Column(String(255), nullable= True)

    __table_args__ = (
        # Named Primary Key Constraint
        # PrimaryKeyConstraint('mpi', name='pk_hospital_staff_id'), # we id do this then we have to remove the primary_key=True woord from the mpi above.

        UniqueConstraint('hospital_id', 'nic', name='uq_hospital_nic'),
    )

    visiting_notes = relationship("VisitingNotes", back_populates="patient")
    hospital = relationship("Hospital", back_populates="patient")

class Bill(Base): # Total Bill
    __tablename__ = 'bill'

    bill_id = Column(Integer, primary_key=True, index=True)

    consultation_amount = Column(Float, nullable=False, server_default='0.0') # service amount, lab amount(1000+2000 = 3000))
    lab_charges = Column(Float, nullable=True, server_default='0.0')
    bill_status = Column(String(10), default="Unpaid") # "Paid" or "Unpaid" or "In Process" or "Denied"
    bill_date = Column(DateTime, default=datetime.now())

    visiting_notes = relationship("VisitingNotes", back_populates="bill")

class VisitingNotes(Base):
    __tablename__ = 'visiting_notes'

    note_id = Column(Integer, primary_key=True, index=True)

    mpi = Column(Integer,ForeignKey('patient.mpi', name='fk_visiting_notes_mpi'), nullable=False)
    users_id = Column(Integer, ForeignKey('users.users_id', name='fk_visiting_notes_users_id'), nullable=False)
    bill_id = Column(Integer, ForeignKey('bill.bill_id', name='fk_visiting_notes_bill_id'), nullable=True)

    visit_date = Column(DateTime, default=datetime.now())
    note_title = Column(String(1000), nullable=True)
    patient_complaint = Column(String(255), nullable=True)
    dignosis = Column(String(255), nullable=True)
    note_details = Column(String(1000), nullable=True)
    
    hospital_id = Column(String(50), ForeignKey('hospital.hospital_id', name='fk_visiting_notes_hospital_id'), nullable=False)

    user = relationship("Users", back_populates="visiting_notes")
    patient = relationship("Patient", back_populates="visiting_notes")
    bill = relationship("Bill", back_populates="visiting_notes")
    report = relationship("LabReport", back_populates="visiting_notes")
    hospital = relationship("Hospital", back_populates="visiting_notes")

class LoincMaster(Base):
    __tablename__ = "loinc_master"

    loinc_code       = Column(String(10),  primary_key=True, index=True)
    long_common_name = Column(Text, nullable=False)
    short_name       = Column(String(150), nullable=True)
    component        = Column(String(200), nullable=True)  # what is being measured ("WBC, RBC, Glucose")
    system           = Column(String(500), nullable=True)  # The specimen from which the measurement is taken (Blood, Urine, etc.)  

    @property
    def display_name(self) -> str:
        """Short display name safe for mobile — never null."""
        if self.short_name:
            return self.short_name
        if self.component and self.system:
            return f"{self.component} ({self.system})"
        if self.component:
            return self.component
        return self.long_common_name[:50]

    @property
    def mobile_name(self) -> str:
        """Hard cap at 40 chars for very narrow screens."""
        name = self.display_name
        return name if len(name) <= 40 else name[:37] + "..."
    
    @mobile_name.setter
    def mobile_name(self, value):
        pass  # this is use for validation whenever someone do like this: obj.mobile_name = "some_value"

    def to_dict(self) -> dict:
        return {
            "loinc_code":       self.loinc_code,
            "long_common_name": self.long_common_name,
            "display_name":     self.display_name,   # for desktop
            "mobile_name":      self.mobile_name,    # for mobile
            "component":        self.component,
            "system":           self.system,
        }

class LabReport(Base): 
    # add the lab results column here as well (description, bill amount, amount_status(paid or not paid) )
    __tablename__ = "lab_report"

    report_id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(Integer, ForeignKey('visiting_notes.note_id', name='fk_lab_report_visit_id'), nullable=False)
    loinc_code = Column(String(10), ForeignKey('loinc_master.loinc_code', name='fk_lab_report_loinc_code'), nullable=False)

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
    report_id = Column(Integer, ForeignKey("lab_report.report_id", name='fk_mini_test_result_report_id'), nullable=False)

    test_name = Column(String(50), nullable=False)
    normal_range = Column(String(20), nullable=False)
    result_value = Column(String(7), nullable=False)
    unit = Column(String(20), nullable=False)

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
