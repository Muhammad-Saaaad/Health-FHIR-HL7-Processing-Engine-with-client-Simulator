import os
from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL_ENGINE")

# engine = create_engine(DATABASE_URL)
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,       # Use QueuePool for connection pooling important for handling concurrent requests.
    pool_size=25,              # Base connections
    max_overflow=50,           # Temp connections
    pool_pre_ping=True,        # Health check
    pool_recycle=3600,         # Recycle hourly
)
session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base() 

def get_db():
    db = session_local()
    try:
        yield db
    finally:
        db.close()