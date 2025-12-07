import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL_EMR")
engine = create_engine(DATABASE_URL)
session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, pool_pre_ping=True)

def get_db():
    db = session_local()
    try:
        yield db
    finally:
        db.close()