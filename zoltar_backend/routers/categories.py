from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Use absolute imports within the same package structure
from zoltar_backend import crud, models, schemas, auth
from zoltar_backend.database import get_db

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
    dependencies=[Depends(auth.get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.Category, status_code=status.HTTP_201_CREATED)
def create_category(
    category: schemas.CategoryCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return crud.create_user_category(db=db, category=category, user_id=current_user.id)

@router.get("/", response_model=List[schemas.Category])
def read_categories(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_active_user)
):
    categories = crud.get_user_categories(db, user_id=current_user.id, skip=skip, limit=limit)
    return categories

@router.get("/{category_id}", response_model=schemas.Category)
def read_category(
    category_id: int, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_active_user)
):
    db_category = crud.get_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if db_category.owner_id != current_user.id:
        # Although the get_user_categories filters, this direct access needs owner check
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this category")
    return db_category

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_active_user)
):
    deleted = crud.delete_category(db=db, category_id=category_id, user_id=current_user.id)
    if not deleted:
        # This covers both "not found" and "not owned" cases for deletion attempt
        raise HTTPException(status_code=404, detail="Category not found or not owned by user")
    return # Return None for 204 response 