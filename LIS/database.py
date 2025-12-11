import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL_LIS"))
local_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = local_session()
    try:
        yield db
    finally:
        db.close()