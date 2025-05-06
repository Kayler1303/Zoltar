from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from zoltar_backend import crud, models, schemas, auth
from zoltar_backend.database import get_db

router = APIRouter(
    prefix="/lists",
    tags=["lists"],
    dependencies=[Depends(auth.get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

# --- List Endpoints ---

@router.post("/", response_model=schemas.List)
def create_list(
    list_data: schemas.ListCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Creates a new list for the current user."""
    return crud.create_list(db=db, list_data=list_data, user_id=current_user.id)

@router.get("/", response_model=List[schemas.List])
def read_lists(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves all lists for the current user."""
    return crud.get_lists_by_user(db=db, user_id=current_user.id)

@router.get("/{list_id}", response_model=schemas.List)
def read_list(
    list_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves a specific list by ID for the current user."""
    db_list = crud.get_list(db=db, list_id=list_id, user_id=current_user.id)
    if db_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return db_list

@router.put("/{list_id}", response_model=schemas.List)
def update_list(
    list_id: int,
    list_data: schemas.ListUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Updates a specific list for the current user."""
    db_list = crud.update_list(db=db, list_id=list_id, list_data=list_data, user_id=current_user.id)
    if db_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    return db_list

@router.delete("/{list_id}", response_model=dict)
def delete_list(
    list_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Deletes a specific list for the current user."""
    deleted = crud.delete_list(db=db, list_id=list_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="List not found")
    return {"ok": True}

# --- ListItem Endpoints ---

@router.post("/{list_id}/items/", response_model=schemas.ListItem)
def create_list_item(
    list_id: int,
    item_data: schemas.ListItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Creates a new item within a specific list owned by the current user."""
    result = crud.create_list_item(db=db, item_data=item_data, list_id=list_id, user_id=current_user.id)
    if result == "list_not_found":
        raise HTTPException(status_code=404, detail="Parent list not found or not owned by user")
    # Assuming result is the db_item on success
    return result

@router.put("/items/{item_id}", response_model=schemas.ListItem)
def update_list_item(
    item_id: int,
    item_data: schemas.ListItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Updates a specific list item owned by the current user (via parent list)."""
    result = crud.update_list_item(db=db, item_id=item_id, item_data=item_data, user_id=current_user.id)
    if result == "item_not_found":
        raise HTTPException(status_code=404, detail="List item not found or not owned by user")
    # Assuming result is the db_item on success
    return result

@router.delete("/items/{item_id}", response_model=dict)
def delete_list_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Deletes a specific list item owned by the current user (via parent list)."""
    deleted = crud.delete_list_item(db=db, item_id=item_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="List item not found or not owned by user")
    return {"ok": True} 