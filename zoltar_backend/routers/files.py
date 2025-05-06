import os
import uuid
import shutil
from pathlib import Path

from fastapi import (
    APIRouter, Depends, HTTPException, status, UploadFile, File
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# Use absolute imports relative to the package root
from zoltar_backend import crud, models, schemas, auth
from zoltar_backend.database import get_db
from zoltar_backend import llm_utils, file_utils # Import new utils
import logging # Import logging if not already present

# Define the base directory for uploads relative to the project root
# Assuming the server runs from the project root (where zoltar_backend/ is)
UPLOAD_DIR = Path("./uploads") 

router = APIRouter(
    prefix="/files",
    tags=["files"],
    dependencies=[Depends(auth.get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

logger = logging.getLogger(__name__)

@router.post("/upload", response_model=schemas.FileReference, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...), # File is required
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Handles file uploads, saves the file locally, and creates a DB reference."""
    
    # Create user-specific upload directory
    user_upload_dir = UPLOAD_DIR / str(current_user.id)
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    _, file_extension = os.path.splitext(file.filename)
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
    storage_path = user_upload_dir / unique_filename
    relative_storage_path = Path('.') / storage_path # Store relative path in DB

    # Save the file
    try:
        with storage_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        # Basic error handling, consider more specific exceptions
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not save file: {e}")
    finally:
        file.file.close() # Ensure the file buffer is closed

    # Get file metadata (size might be available directly)
    file_size = storage_path.stat().st_size
    file_type = file.content_type

    # Create database reference
    db_file_ref = crud.create_file_reference(
        db=db,
        owner_id=current_user.id,
        original_filename=file.filename,
        storage_path=str(relative_storage_path), # Store as string
        file_type=file_type,
        file_size=file_size
    )

    return db_file_ref

@router.get("/{file_id}", response_model=schemas.FileReference)
def get_file_metadata(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves metadata for a file by its ID, checking ownership."""
    db_file_ref = crud.get_file_reference(db, file_id=file_id)

    if db_file_ref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File record not found")

    if db_file_ref.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this file")

    #     # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")
    
    # Return the Pydantic schema object (FastAPI handles serialization)
    print(f"DEBUG: Returning FileReference metadata for ID: {file_id}")
    return db_file_ref
    # --- End metadata return --- 
    
    # --- OLD CODE returning FileResponse ---
    # return FileResponse(
    #     path=file_path, 
    #     filename=db_file_ref.original_filename, 
    #     media_type=db_file_ref.file_type # Use stored media type if available
    # )
    # --- End OLD CODE --- 

@router.put("/{file_id}", response_model=schemas.FileReference)
def update_file_links(
    file_id: int,
    update_data: schemas.FileReferenceUpdate, # Request body
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Links/unlinks a file to a project or task."""
    updated_file_ref = crud.update_file_reference_links(
        db=db, user_id=current_user.id, file_id=file_id, update_data=update_data
    )

    if updated_file_ref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File record not found")
    if updated_file_ref == "unauthorized_file":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this file")
    if updated_file_ref == "invalid_project":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not found or not owned by user")
    if updated_file_ref == "invalid_task":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task not found or not owned by user")

    return updated_file_ref # Return the updated FileReference object 

# --- Add Summarization Endpoint ---
@router.post("/{file_id}/summarize", response_model=schemas.FileSummaryResponse)
def summarize_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Extracts text from a file and generates a summary using the LLM."""
    logger.info(f"Summarization request for file_id {file_id} by user {current_user.email}")
    
    # 1. Get File Record
    db_file_ref = crud.get_file_reference(db, file_id=file_id)
    if db_file_ref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File record not found")
    if db_file_ref.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this file")

    # 2. Construct Full File Path
    # Assumes server runs from project root where UPLOAD_DIR is defined
    file_path = Path(db_file_ref.storage_path).resolve() 
    logger.debug(f"Resolved file path for summarization: {file_path}")

    # 3. Extract Text
    extracted_text = file_utils.extract_text_from_file(str(file_path))
    if extracted_text is None:
        logger.error(f"Failed to extract text from file: {file_path} (ID: {file_id})")
        # Return response indicating failure but not a server error
        return schemas.FileSummaryResponse(
            file_id=file_id, 
            summary=None, 
            error="Could not extract text from file. It might be missing, unsupported, or corrupted."
        )
    
    logger.info(f"Successfully extracted text from file ID {file_id}. Length: {len(extracted_text)}")

    # 4. Summarize Text
    summary = llm_utils.summarize_text_gemini(extracted_text)
    if summary is None:
        logger.error(f"Failed to generate summary for file ID {file_id}")
        return schemas.FileSummaryResponse(
            file_id=file_id, 
            summary=None, 
            error="Failed to generate summary using the LLM. Check API key or LLM service status."
        )

    # 5. Return Success Response
    logger.info(f"Successfully generated summary for file ID {file_id}")
    return schemas.FileSummaryResponse(file_id=file_id, summary=summary, error=None) 