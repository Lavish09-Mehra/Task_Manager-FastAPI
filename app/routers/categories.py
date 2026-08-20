# app/routers/categories.py
# =====================================================================
# CATEGORY ROUTES.
#
# Same ownership-scoping pattern as tasks.py: EVERY query includes
# `Category.owner_id == user.id` in the WHERE clause, so one user can
# never see, edit or delete another user's categories.
#
# A category is simply a user-owned label ("Work", "Personal", ...).
# Deleting a category does NOT delete the tasks that used it - thanks to
# ondelete="SET NULL" the tasks keep existing with category_id = NULL.
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
    """Fetch a category that belongs to `user`, or raise 404.

    The ownership check happens INSIDE the SQL:
        WHERE categories.id = ? AND categories.owner_id = ?
    so guessing someone else's id just returns 'not found'.
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
    # db.scalars(...).all() -> every matching row as Category objects.
    # Ordered alphabetically by name for a stable, friendly UI order.
    return db.scalars(
        select(Category).where(Category.owner_id == user.id).order_by(Category.name)
    ).all()


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new category (name must be unique per user)."""

    # Pre-flight duplicate check for a friendlier error. (The composite
    # UNIQUE index in models.py would also reject duplicates at the DB
    # level - trust, but verify, and give users a nice message first.)
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

    # Note: `name` here is already STRIPPED by the Pydantic field_validator
    # (schemas.py), so "Work" and "  Work" both map to "Work".
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
    """Get one category by id (only if it's the caller's)."""
    return _get_owned_category(db, category_id, user)


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a category's name and/or color.

    Same partial-update mechanic as tasks: exclude_unset=True -> only the
    fields the client actually sent are assigned; everything else stays
    untouched.
    """

    category = _get_owned_category(db, category_id, user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)

    db.commit()       # category is tracked -> UPDATE on commit
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a category. Its tasks are KEPT (category becomes NULL)."""

    category = _get_owned_category(db, category_id, user)

    # ondelete="SET NULL" (models.py) makes PostgreSQL itself set
    # tasks.category_id = NULL on all referring tasks, atomically within
    # the DELETE. No manual bookkeeping needed.
    db.delete(category)
    db.commit()
    # 204 responses must not return a body.