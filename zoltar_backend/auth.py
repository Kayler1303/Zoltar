import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

# Revert to relative imports
from . import crud 
from . import models 
from . import schemas 
from .database import get_db

load_dotenv()

# Read secret key from file path specified in env var
SECRET_KEY_PATH = os.getenv("SECRET_KEY_PATH", "/secrets/jwt/key") # Default path if not set
SECRET_KEY = None
try:
    with open(SECRET_KEY_PATH, 'r') as f:
        SECRET_KEY = f.read().strip()
    if not SECRET_KEY:
        print(f"ERROR: Secret key file {SECRET_KEY_PATH} is empty.")
        # Decide how to handle - exit? raise error?
except FileNotFoundError:
    print(f"ERROR: Secret key file not found at {SECRET_KEY_PATH}. Ensure SECRET_KEY_PATH env var is set correctly and the secret is mounted.")
    # Decide how to handle
except Exception as e:
    print(f"ERROR: Could not read secret key from {SECRET_KEY_PATH}: {e}")
    # Decide how to handle

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# JWT Token Handling
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Added: OAuth2 Scheme and Dependency Functions --- 
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        # Removed TokenData validation here as we only need the email (sub)
        # token_data = schemas.TokenData(email=email) # This line is optional if only sub is needed
    except JWTError:
        raise credentials_exception
    user = crud.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# --- End Added ---

# Placeholder for authentication logic (will be expanded)
# def get_current_user(...):
#     pass 