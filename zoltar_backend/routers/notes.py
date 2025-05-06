from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

# Zoltar imports
from .. import crud, models, schemas, auth, llm_utils
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/notes",
    tags=["Notes"],
    dependencies=[Depends(auth.get_current_active_user)], # Require Zoltar auth
    responses={404: {"description": "Note not found"}},
)

@router.post("/", response_model=schemas.Note, status_code=status.HTTP_201_CREATED)
def create_note(
    note: schemas.NoteCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Create a new note for the current user."""
    logger.info(f"User {current_user.email} creating note.")
    result = crud.create_user_note(db=db, note=note, user_id=current_user.id)
    if isinstance(result, str):
        if result == "invalid_contact":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid contact_id: {note.contact_id}. Contact not found or does not belong to user.")
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")
    logger.info(f"Note created with ID: {result.id} for user {current_user.email}")
    return result

@router.get("/", response_model=List[schemas.Note])
def read_notes(
    contact_id: Optional[int] = Query(None, description="Filter notes by contact ID"),
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieve notes for the current user, optionally filtered by contact ID."""
    logger.info(f"User {current_user.email} reading notes. Filter by contact_id: {contact_id}")
    notes = crud.get_user_notes(db, user_id=current_user.id, contact_id=contact_id, skip=skip, limit=limit)
    return notes

@router.get("/{note_id}", response_model=schemas.Note)
def read_note(
    note_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieve a specific note by ID."""
    logger.info(f"User {current_user.email} reading note ID: {note_id}")
    db_note = crud.get_note(db, note_id=note_id, user_id=current_user.id)
    if db_note is None:
        logger.warning(f"Note ID {note_id} not found for user {current_user.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return db_note

@router.put("/{note_id}", response_model=schemas.Note)
def update_note(
    note_id: int, 
    note: schemas.NoteUpdate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Update a specific note by ID."""
    logger.info(f"User {current_user.email} updating note ID: {note_id}")
    result = crud.update_note(db=db, note_id=note_id, note_update=note, user_id=current_user.id)
    if result is None:
        logger.warning(f"Note ID {note_id} not found for user {current_user.email} during update.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if isinstance(result, str):
        if result == "invalid_contact":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid contact_id provided in update. Contact not found or does not belong to user.")
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred during update.")
    logger.info(f"Note ID {note_id} updated successfully for user {current_user.email}")
    return result

@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Delete a specific note by ID."""
    logger.info(f"User {current_user.email} deleting note ID: {note_id}")
    deleted = crud.delete_note(db=db, note_id=note_id, user_id=current_user.id)
    if not deleted:
        logger.warning(f"Note ID {note_id} not found for user {current_user.email} during delete attempt.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    logger.info(f"Note ID {note_id} deleted successfully by user {current_user.email}")
    return # Return None with 204 status code 

@router.post("/summary", response_model=schemas.NoteSummaryResponse)
async def summarize_notes(
    summary_request: schemas.NoteSummaryRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Summarizes notes based on provided filters (note_ids, source, tags)."""
    logger.info(f"Received request to summarize notes for user {current_user.email} with filters: {summary_request.model_dump()}")

    # 1. Call crud function to get note IDs and combined content based on filters
    try:
        included_ids, combined_content = crud.get_notes_content_by_filter(
            db=db, user_id=current_user.id, filters=summary_request
        )
    except Exception as e:
        logger.error(f"Error retrieving notes for summarization: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve notes for summarization.")

    # 2. Handle case where no notes are found
    if not included_ids or not combined_content:
        logger.info(f"No notes found matching filter criteria for user {current_user.email}")
        return schemas.NoteSummaryResponse(
            summary="No notes match the filter criteria.",
            included_note_ids=[]
        )
        
    logger.info(f"Summarizing content from {len(included_ids)} notes for user {current_user.email}. Total length: {len(combined_content)} chars.")

    # 3. Call LLM utility function to summarize combined content
    # Note: Currently ignoring summary_request.max_summary_length as the LLM function doesn't support it yet.
    summary = llm_utils.summarize_text_gemini(text_to_summarize=combined_content)

    # 4. Handle LLM failure
    if summary is None:
        logger.error(f"LLM summarization failed for notes: {included_ids}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to generate summary due to LLM error.")

    # 5. Return NoteSummaryResponse
    logger.info(f"Successfully generated summary for notes: {included_ids}")
    return schemas.NoteSummaryResponse(
        summary=summary,
        included_note_ids=included_ids
    )

# Potentially add other note-related endpoints here 