import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables from .env file (optional, good for local dev)
load_dotenv()

# --- Get DATABASE_URL from environment variable ---
# Use a sensible default for local SQLite if the env var isn't set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./zoltar.db")

# --- Adjust engine creation based on URL ---
if DATABASE_URL.startswith("postgresql"):
    # For PostgreSQL (or other DBs needing connection pooling/args)
    engine = create_engine(
        DATABASE_URL
        # Example: Add connection pool arguments if needed for production
        # pool_size=10,
        # max_overflow=20
    )
else:
    # For SQLite (requires connect_args)
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
# --- End adjustments ---

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 