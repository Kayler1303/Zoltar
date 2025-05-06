from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Change to direct imports
import crud
import models
import schemas
import auth
from database import get_db

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(auth.get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.Task, status_code=status.HTTP_201_CREATED)
def create_task(
    task: schemas.TaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_task = crud.create_user_task(db=db, task=task, user_id=current_user.id)
    if db_task is None: # Handle invalid project case from CRUD
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not found or not owned by user")
    return db_task

@router.get("/", response_model=List[schemas.Task])
def read_tasks(
    skip: int = 0,
    limit: int = 100,
    # Add project_id, status filters later
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    tasks = crud.get_user_tasks(db, user_id=current_user.id, skip=skip, limit=limit)
    return tasks

@router.get("/available", response_model=List[schemas.Task])
def read_available_tasks(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves tasks for the user that are currently available (Pending or In Progress)."""
    tasks = crud.get_user_available_tasks(db=db, user_id=current_user.id)
    return tasks

@router.get("/{task_id}", response_model=schemas.Task)
def read_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_task = crud.get_task(db, task_id=task_id)
    if db_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if db_task.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this task")
    return db_task

@router.put("/{task_id}", response_model=schemas.TaskUpdateResponse)
def update_task(
    task_id: int,
    task_update: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    update_result = crud.update_task(
        db=db, task_id=task_id, task_update=task_update, user_id=current_user.id
    )
    
    # Check for error conditions returned by CRUD function
    if update_result is None: # Handle task not found/owned
        raise HTTPException(status_code=404, detail="Task not found or not owned by user")
    if isinstance(update_result, str) and update_result == "invalid_project": # Handle invalid project during update
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not found or not owned by user")
        
    # If successful, update_result is the dictionary {"updated_task": ..., "unblocked_tasks": ...}
    # FastAPI will automatically convert this dict to the TaskUpdateResponse schema
    return update_result

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    deleted = crud.delete_task(db=db, task_id=task_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found or not owned by user")
    return # Return None for 204 response 

# --- Task Dependency Endpoints ---

@router.post("/{task_id}/depends_on/{depends_on_task_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_task_dependency_endpoint(
    task_id: int,
    depends_on_task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Make task_id dependent on depends_on_task_id."""
    result = crud.add_task_dependency(db, task_id, depends_on_task_id, current_user.id)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or both tasks not found or not owned by user")
    if result == "self_dependency":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task cannot depend on itself")
    if result == "already_exists":
        # Not an error, just return success (idempotent)
        pass 
    elif result != "ok":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add dependency") # Should not happen
    return

@router.delete("/{task_id}/depends_on/{depends_on_task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_task_dependency_endpoint(
    task_id: int,
    depends_on_task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Remove dependency of task_id on depends_on_task_id."""
    result = crud.remove_task_dependency(db, task_id, depends_on_task_id, current_user.id)
    if result == "not_found":
         # If either task not found, or dependency doesn't exist, return 404
         # Distinguishing could be done in CRUD, but 404 is acceptable here.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or both tasks not found, or dependency does not exist")
    elif result != "ok":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove dependency") # Should not happen
    return 