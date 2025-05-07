import os
import logging # Import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Get a logger instance
# The basicConfig in main.py should allow these messages to appear
db_module_logger = logging.getLogger(__name__)

# Load environment variables from .env file (optional, good for local dev)
load_dotenv()

# --- Get DATABASE_URL from environment variable ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./zoltar.db")
db_module_logger.info(f"database.py: DATABASE_URL read from environment: '{DATABASE_URL}'") # ADDED LOGGING

# --- Adjust engine creation based on URL ---
if DATABASE_URL.startswith("postgresql"):
    db_module_logger.info("database.py: Configuring engine for PostgreSQL with sslmode=disable.") # ADDED LOGGING
    engine = create_engine(
        DATABASE_URL,
        connect_args={"sslmode": "disable"}
        # Example: Add connection pool arguments if needed for production
        # pool_size=10,
        # max_overflow=20
    )
else:
    # For SQLite (requires connect_args)
    db_module_logger.info(f"database.py: Configuring engine for non-PostgreSQL (e.g., SQLite). Current DATABASE_URL: '{DATABASE_URL}'") # ADDED LOGGING
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