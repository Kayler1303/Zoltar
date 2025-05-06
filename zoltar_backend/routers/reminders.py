from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

# Change to direct imports
import crud
import models
import schemas
import auth
from database import get_db

router = APIRouter(
    prefix="/reminders",
    tags=["reminders"],
    dependencies=[Depends(auth.get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.Reminder, status_code=status.HTTP_201_CREATED)
def create_reminder(
    reminder: schemas.ReminderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    result = crud.create_user_reminder(db=db, reminder=reminder, user_id=current_user.id)
    if result == "invalid_task":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task not found or not owned by user")
    if result == "invalid_file":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File not found or not owned by user")
    if result == "invalid_rule":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or missing recurrence rule for recurring reminder")
    # Assuming direct return of the object on success
    return result 

@router.get("/", response_model=List[schemas.Reminder])
def read_reminders(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    reminders = crud.get_user_reminders(db, user_id=current_user.id, skip=skip, limit=limit)
    return reminders

@router.get("/{reminder_id}", response_model=schemas.Reminder)
def read_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_reminder = crud.get_reminder(db, reminder_id=reminder_id)
    if db_reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if db_reminder.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this reminder")
    return db_reminder

@router.put("/{reminder_id}", response_model=schemas.Reminder)
def update_reminder(
    reminder_id: int,
    reminder_update: schemas.ReminderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    updated_reminder = crud.update_reminder(
        db=db, reminder_id=reminder_id, reminder_update=reminder_update, user_id=current_user.id
    )
    if updated_reminder is None: # Handle reminder not found/owned
        raise HTTPException(status_code=404, detail="Reminder not found or not owned by user")
    if updated_reminder == "invalid_task":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task not found or not owned by user")
    if updated_reminder == "invalid_file":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File not found or not owned by user")
    if updated_reminder == "invalid_rule":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or missing recurrence rule, or rule provided for one-time reminder")
    return updated_reminder

@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    deleted = crud.delete_reminder(db=db, reminder_id=reminder_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Reminder not found or not owned by user")
    return # Return None for 204 response 

# --- Action Endpoints ---

@router.post("/{reminder_id}/complete", response_model=schemas.Reminder)
def complete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Marks the current instance of a reminder as complete. For recurring scheduled, reschedules to next occurrence."""
    result = crud.complete_reminder_instance(db=db, reminder_id=reminder_id, user_id=current_user.id)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found or not owned by user")
    if result == "inactive":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reminder is already inactive")
    return result

@router.post("/{reminder_id}/skip", response_model=schemas.Reminder)
def skip_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Skips the current instance of a reminder. For recurring scheduled, reschedules to next occurrence."""
    result = crud.skip_reminder_instance(db=db, reminder_id=reminder_id, user_id=current_user.id)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found or not owned by user")
    if result == "inactive":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reminder is already inactive")
    return result 

# --- History Endpoint ---

@router.get("/{reminder_id}/history", response_model=List[schemas.ReminderEvent])
def read_reminder_history(
    reminder_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves the action history for a specific reminder."""
    history_result = crud.get_reminder_history(
        db=db,
        reminder_id=reminder_id,
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date
    )
    if history_result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found or not owned by user")
    # Assuming direct return of list on success
    return history_result 