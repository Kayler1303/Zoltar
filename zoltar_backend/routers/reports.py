from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Use absolute imports relative to the package root
from zoltar_backend import crud, models, schemas, auth
from zoltar_backend.database import get_db

router = APIRouter(
    prefix="/outstanding",
    tags=["outstanding items"],
    dependencies=[Depends(auth.get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

@router.get("/contact/{contact_id}", response_model=schemas.OutstandingItemsResponse)
def read_outstanding_items_for_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Retrieves outstanding tasks and reminders associated with a specific contact ID."""
    items = crud.get_outstanding_items_for_contact(db=db, contact_id=contact_id, user_id=current_user.id)
    if items is None: # CRUD function returns None if contact not found/owned
        raise HTTPException(status_code=404, detail="Contact not found or not owned by user")
    return items

# Add endpoint for /outstanding/{person_name} later, requiring name lookup logic in CRUD
# Add filtering (e.g., by item type) later if needed 