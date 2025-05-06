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
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(auth.get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.Project, status_code=status.HTTP_201_CREATED)
def create_project(
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_project = crud.create_user_project(db=db, project=project, user_id=current_user.id)
    if db_project is None: # Handle invalid category case from CRUD
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or not owned by user")
    return db_project

@router.get("/", response_model=List[schemas.Project])
def read_projects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    projects = crud.get_user_projects(db, user_id=current_user.id, skip=skip, limit=limit)
    return projects

@router.get("/by_category", response_model=schemas.ProjectsByCategoryResponse)
def read_projects_by_category(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves all projects for the user, grouped by category."""
    grouped_projects = crud.get_user_projects_by_category(db=db, user_id=current_user.id)
    return grouped_projects

@router.get("/{project_id}", response_model=schemas.Project)
def read_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_project = crud.get_project(db, project_id=project_id)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if db_project.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this project")
    return db_project

@router.get("/{project_id}/summary", response_model=schemas.ProjectSummaryResponse)
def read_project_summary(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves a structured summary for a specific project."""
    summary_data = crud.get_project_summary(db=db, project_id=project_id, user_id=current_user.id)
    if summary_data is None:
        raise HTTPException(status_code=404, detail="Project not found or not owned by user")
    # The CRUD function returns a dict; FastAPI validates it against ProjectSummaryResponse
    return summary_data

@router.put("/{project_id}", response_model=schemas.ProjectUpdateResponse)
def update_project(
    project_id: int,
    project_update: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    update_result = crud.update_project(
        db=db, project_id=project_id, project_update=project_update, user_id=current_user.id
    )
    
    # Check for error conditions returned by CRUD function
    if update_result is None: # Handle project not found/owned
        raise HTTPException(status_code=404, detail="Project not found or not owned by user")
    if isinstance(update_result, str) and update_result == "invalid_category": # Handle invalid category during update
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or not owned by user")
    
    # If successful, update_result is the dictionary {"updated_project": ..., "unblocked_projects": ...}
    # FastAPI will automatically convert this dict to the ProjectUpdateResponse schema
    return update_result

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    deleted = crud.delete_project(db=db, project_id=project_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found or not owned by user")
    return # Return None for 204 response 

# --- Project Dependency Endpoints ---

@router.post("/{project_id}/depends_on/{depends_on_project_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_project_dependency_endpoint(
    project_id: int,
    depends_on_project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Make project_id dependent on depends_on_project_id."""
    result = crud.add_project_dependency(db, project_id, depends_on_project_id, current_user.id)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or both projects not found or not owned by user")
    if result == "self_dependency":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project cannot depend on itself")
    if result == "already_exists":
        pass # Idempotent
    elif result != "ok":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add dependency")
    return

@router.delete("/{project_id}/depends_on/{depends_on_project_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_dependency_endpoint(
    project_id: int,
    depends_on_project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Remove dependency of project_id on depends_on_project_id."""
    result = crud.remove_project_dependency(db, project_id, depends_on_project_id, current_user.id)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or both projects not found, or dependency does not exist")
    elif result != "ok":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove dependency")
    return 