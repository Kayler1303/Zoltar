import os
import logging # Import logging
from sqlalchemy import create_engine, text # Add text for diagnostic query
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
engine = None # Initialize engine

if DATABASE_URL.startswith("postgresql"):
    db_module_logger.info("database.py: Configuring engine for PostgreSQL (no explicit sslmode).") # MODIFIED LOG
    engine = create_engine(DATABASE_URL) # REMOVED connect_args

elif DATABASE_URL: # Modified to ensure engine is always assigned if DATABASE_URL is not empty
    db_module_logger.info(f"database.py: Configuring engine for non-PostgreSQL (e.g., SQLite). Current DATABASE_URL: '{DATABASE_URL}'") # ADDED LOGGING
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else: # Handle case where DATABASE_URL is empty after os.getenv (if default was removed)
    db_module_logger.error("database.py: DATABASE_URL is empty. Cannot create engine.")
    raise ValueError("DATABASE_URL environment variable is not set and no default provided.") # Make it fatal

if engine is None:
    # This case should ideally not be reached if DATABASE_URL is always set or has a default
    db_module_logger.critical("database.py: Engine was not initialized!")
    # Consider raising an error here to prevent the app from starting with no engine
    raise RuntimeError("SQLAlchemy engine could not be initialized.")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 