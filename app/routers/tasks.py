# app/routers/tasks.py
# =====================================================================
# Task endpoints (the "meat" of the CRUD app).
#
# Query scoping pattern: EVERY query filters by `user.id` so no user can
# read or modify another user's tasks - even by guessing an id.
# =====================================================================

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Category, Task, TaskPriority, TaskStatus, User
from app.schemas import TaskCreate, TaskOut, TaskPage, TaskStats, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_owned_task(db: Session, task_id: int, user: User) -> Task:
    """Load a task that belongs to `user`, else raise 404."""
    task = db.scalar(
        select(Task).where(Task.id == task_id, Task.owner_id == user.id)
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---------------------------------------------------------------------
# LIST (with filtering + pagination)
# ---------------------------------------------------------------------
@router.get("", response_model=TaskPage)
def list_tasks(
    # --- filters (all optional) ---
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    priority: Optional[TaskPriority] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = Query(None, description="match title/description"),
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    # --- pagination ---
    page: int = Query(1, ge=1),                 # page number, min 1
    size: int = Query(10, ge=1, le=100),        # items per page, 1..100
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the current user's tasks with optional filters."""

    # Base query: only tasks owned by this user.
    stmt = select(Task).where(Task.owner_id == user.id)

    # Apply each filter (only if the parameter was provided).
    if status_filter is not None:
        stmt = stmt.where(Task.status == status_filter)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if category_id is not None:
        stmt = stmt.where(Task.category_id == category_id)
    if search:
        # ILIKE = case-insensitive LIKE. %..% = "contains".
        like = f"%{search}%"
        stmt = stmt.where(
            (Task.title.ilike(like)) | (Task.description.ilike(like))
        )
    if due_from is not None:
        stmt = stmt.where(Task.due_date >= due_from)
    if due_to is not None:
        stmt = stmt.where(Task.due_date <= due_to)

    # Total count BEFORE pagination (needed for pagination metadata).
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))

    # Order: incomplete first (pending > in_progress > completed),
    # then by urgency (urgent > high > medium > low), then newest first.
    stmt = stmt.order_by(
        Task.status.asc(),
        Task.priority.desc(),
        Task.created_at.desc(),
    ).offset((page - 1) * size).limit(size)

    items = db.scalars(stmt).all()

    return TaskPage(total=total, page=page, size=size, items=items)


# ---------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------
@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new task owned by the current user."""

    # Validate category_id if provided -> must exist AND belong to user.
    if payload.category_id is not None:
        category = db.scalar(
            select(Category).where(
                Category.id == payload.category_id, Category.owner_id == user.id
            )
        )
        if category is None:
            raise HTTPException(status_code=400, detail="Invalid category_id")

    task = Task(**payload.model_dump(), owner_id=user.id)
    db.add(task)
    db.commit()
    db.refresh(task)   # load id, created_at (and category for the response)
    return task


# ---------------------------------------------------------------------
# READ one
# ---------------------------------------------------------------------
@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single task (only if it belongs to the current user)."""
    return _get_owned_task(db, task_id, user)


# ---------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------
@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a task - partial updates allowed (only sent fields change)."""

    task = _get_owned_task(db, task_id, user)

    # Validate category_id the same way as create, if it was sent.
    if payload.category_id is not None:
        category = db.scalar(
            select(Category).where(
                Category.id == payload.category_id, Category.owner_id == user.id
            )
        )
        if category is None:
            raise HTTPException(status_code=400, detail="Invalid category_id")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
    return task


# ---------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------
@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a task. Returns 204 with an empty body on success."""
    task = _get_owned_task(db, task_id, user)
    db.delete(task)
    db.commit()
    # 204 responses have no body - so we return None.


# ---------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------
@router.get("/stats/overview", response_model=TaskStats)
def task_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Quick number dashboard for the current user's tasks."""

    # Aggregate status counts in ONE query with GROUP BY (no python loops).
    base = select(Task).where(Task.owner_id == user.id).subquery()
    status_counts = dict(
        db.execute(
            select(base.c.status, func.count()).group_by(base.c.status)
        ).all()
    )

    # Same trick but for priority (count how many HIGH / URGENT tasks).
    def _priority_count(priority_value: TaskPriority) -> int:
        return db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.owner_id == user.id, Task.priority == priority_value)
        ) or 0

    return TaskStats(
        total=sum(status_counts.values()),
        pending=status_counts.get(TaskStatus.PENDING, 0),
        in_progress=status_counts.get(TaskStatus.IN_PROGRESS, 0),
        completed=status_counts.get(TaskStatus.COMPLETED, 0),
        high_priority=_priority_count(TaskPriority.HIGH),
        urgent_priority=_priority_count(TaskPriority.URGENT),
    )