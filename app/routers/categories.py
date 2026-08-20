# app/routers/categories.py
# =====================================================================
# Category endpoints - every route is scoped to the authenticated user.
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Category, Task, User
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


def _get_owned_category(db: Session, category_id: int, user: User) -> Category:
    """Fetch a category that belongs to `user`, else raise 404.

    Owning is checked in the SQL query itself (id AND owner_id) so users
    can never touch someone else's data, even by guessing an id.
    """
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.owner_id == user.id)
    )
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all categories belonging to the current user."""
    return db.scalars(
        select(Category).where(Category.owner_id == user.id).order_by(Category.name)
    ).all()


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new category (unique per user, tracked by DB index)."""

    already = db.scalar(
        select(Category).where(
            Category.owner_id == user.id, Category.name == payload.name
        )
    )
    if already:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Category '{payload.name}' already exists",
        )

    category = Category(name=payload.name, color=payload.color, owner_id=user.id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get one category by id."""
    return _get_owned_category(db, category_id, user)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a category (name / color)."""

    category = _get_owned_category(db, category_id, user)

    # only apply fields that were actually sent (allows partial update)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a category. Its tasks keep existing (category -> NULL)."""

    category = _get_owned_category(db, category_id, user)

    # FK ondelete="SET NULL" handles the tasks automatically at DB level.
    db.delete(category)
    db.commit()
    # 204 must not return a body.