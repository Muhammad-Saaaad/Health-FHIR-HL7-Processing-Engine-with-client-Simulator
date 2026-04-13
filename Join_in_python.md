### 1. Modern SQLAlchemy 2.0 Style (Recommended)
This approach uses the modern `select()` syntax, joining `VisitingNotes` to both `Patient` and `Doctor` in a single query chain.

```python
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from .database import get_db
from . import models

app = FastAPI()

@app.get("/visiting-notes")
def get_all_visiting_notes(db: Session = Depends(get_db)):
    # 1. Create the select statement linking all 3 tables
    statement = (
        select(models.VisitingNotes, models.Patient, models.Doctor)
        .join(models.Patient, models.VisitingNotes.patient_id == models.Patient.id)
        .join(models.Doctor, models.VisitingNotes.doctor_id == models.Doctor.id)
    )
    
    # 2. Execute the query
    results = db.execute(statement).all()
    
    # 3. Format and return the result
    return [
        {
            "note_id": note.id,
            "note_content": note.content,
            "patient_name": patient.name,
            "doctor_name": doctor.name
        }
        for note, patient, doctor in results
    ]
```
---

## 2. Legacy SQLAlchemy 1.x Style
If your FastAPI application is still built on the older db.query() syntax, use this approach:

``` python
@app.get("/visiting-notes-legacy")
def get_all_visiting_notes_legacy(db: Session = Depends(get_db)):
    # Query all 3 models and chain the joins together
    results = (
        db.query(models.VisitingNotes, models.Patient, models.Doctor)
        .join(models.Patient, models.VisitingNotes.patient_id == models.Patient.id)
        .join(models.Doctor, models.VisitingNotes.doctor_id == models.Doctor.id)
        .all()
    )
    
    return [
        {
            "note_id": note.id,
            "note_content": note.content,
            "patient_name": patient.name,
            "doctor_name": doctor.name
        }
        for note, patient, doctor in results
    ]
```

---

## 💡 Pro-Tip: The "FastAPI" Pythonic Way (Using Relationships)

If you have relationship() configured inside your SQLAlchemy models, you can make the code drastically cleaner and let FastAPI automatically parse the joined data into a JSON response:

### Inside your models.py file:
```python
class VisitingNotes(Base):
    __tablename__ = "visiting_notes"
    
    id = Column(Integer, primary_key=True)
    content = Column(String)
    patient_id = Column(Integer, ForeignKey("patient.id"))
    doctor_id = Column(Integer, ForeignKey("doctor.id"))
    
    # Relationships
    patient = relationship("Patient")
    doctor = relationship("Doctor")
```

Now, querying and returning the full object requires no manual mapping loops at all:

```python
from sqlalchemy.orm import joinedload

@app.get("/visiting-notes-clean")
def get_clean_notes(db: Session = Depends(get_db)):
    return db.query(models.VisitingNotes).options(
        joinedload(models.VisitingNotes.patient),
        joinedload(models.VisitingNotes.doctor)
    ).all()
```