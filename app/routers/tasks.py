# app/routers/tasks.py
# =====================================================================
# TASK ROUTES - the "meat" of the CRUD application.
#
# THE #1 SECURITY PATTERN used everywhere in this project:
#
#   EVERY query filters on `user.id` (via owner_id) in the WHERE clause
#   itself:
#
#       SELECT * FROM tasks WHERE id = ? AND owner_id = ?
#
#   So even if a client GUESSES another user's task id, the row is never
#   found and the API answers 404. Never "fetch first, check later".
#
# Each handler takes `user: User = Depends(get_current_user)`, which means
# the request is guaranteed authenticated BEFORE the code runs.
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
    """Shared helper: fetch a task IF it belongs to `user`, else 404.

    Used by GET, PUT and DELETE so the ownership logic lives in exactly
    one place. The WHERE clause includes BOTH id and owner_id.
    """
    task = db.scalar(
        select(Task).where(Task.id == task_id, Task.owner_id == user.id)
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---------------------------------------------------------------------
# LIST (filtering + pagination)
# ---------------------------------------------------------------------
@router.get("", response_model=TaskPage)
def list_tasks(
    # All of these are QUERY parameters (?page=2&status=completed), parsed
    # by FastAPI from the URL. `Optional[X] = None` -> optional.
    # `Query` adds constraints/aliases to specific params.
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    #   alias="status" -> the URL param is ?status=..., but inside our
    #   function we call it status_filter to avoid shadowing the imported
    #   `status` module (commitment: readable code over a nice name).
    priority: Optional[TaskPriority] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = Query(None, description="match title/description"),
    due_from: Optional[date] = None,   # ?due_from=2026-09-01
    due_to: Optional[date] = None,
    # Pagination:
    page: int = Query(1, ge=1),             # >= 1
    size: int = Query(10, ge=1, le=100),    # 1..100 items per page
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the current user's tasks, with optional filters.

    FastAPI builds the ORM SELECT **dynamically**: each filter APPENDS a
    WHERE clause only when its parameter was provided. The final SQL is
    assembled piece by piece - that's one of the nicest things about the
    SQLAlchemy Core `select()` builder.
    """

    # The immutable base query, always scoped to this user.
    stmt = select(Task).where(Task.owner_id == user.id)

    # -- each optional filter extends the WHERE clause ----------------
    if status_filter is not None:
        # TaskStatus enum works directly in comparisons; SQLAlchemy binds
        # its value, e.g.  WHERE tasks.status = 'completed'.
        stmt = stmt.where(Task.status == status_filter)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if category_id is not None:
        stmt = stmt.where(Task.category_id == category_id)
    if search:
        # ILIKE is PostgreSQL's CASE-INSENSITIVE LIKE. %search% means
        # "contains". The pipe | is SQL OR. Empty description (NULL) just
        # doesn't match, which is fine.
        like = f"%{search}%"
        stmt = stmt.where(
            (Task.title.ilike(like)) | (Task.description.ilike(like))
        )
    if due_from is not None:
        stmt = stmt.where(Task.due_date >= due_from)   # not before X
    if due_to is not None:
        stmt = stmt.where(Task.due_date <= due_to)     # not after Y

    # -----------------------------------------------------------------
    # COUNT FIRST, PAGE SECOND.
    # We must know how many rows MATCH *before* applying OFFSET/LIMIT,
    # or the pagination metadata would be wrong. stmt.subquery() turns
    # the filtered SELECT into an inline view:
    #     SELECT count(*) FROM (SELECT ... WHERE ...) AS anon_1
    # -----------------------------------------------------------------
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))

    # ORDERING explains one neat PostgreSQL detail: `status` and
    # `priority` are real database ENUM types (models.py). PostgreSQL
    # orders ENUM values by DECLARATION ORDER, which is exactly the
    # logical order we want -
    #   status ASC    -> pending, then in_progress, then completed
    #   priority DESC -> urgent > high > medium > low
    # So the "least important thing first" rule needs zero extra code.
    #   created_at DESC -> newest first
    stmt = stmt.order_by(
        Task.status.asc(),
        Task.priority.desc(),
        Task.created_at.desc(),
    ).offset((page - 1) * size).limit(size)
    # OFFSET (page-1)*size skips the previous pages; LIMIT size grabs
    # just this page's slice. Classic SQL pagination.

    # db.scalars() returns rows mapped to Python Task objects.
    items = db.scalars(stmt).all()

    # Wrap into the pagination envelope schema.
    return TaskPage(total=total, page=page, size=size, items=items)


# ---------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------
@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,          # validated JSON body
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new task owned by the current user."""

    # If a category_id was sent, verify it exists AND belongs to this
    # user. Otherwise a user could tag tasks with someone else's
    # category, or the FK would fail with an ugly 500 later.
    if payload.category_id is not None:
        category = db.scalar(
            select(Category).where(
                Category.id == payload.category_id, Category.owner_id == user.id
            )
        )
        if category is None:
            # 400 = "the request itself is wrong", not "missing record".
            raise HTTPException(status_code=400, detail="Invalid category_id")

    # payload.model_dump()      -> {"title": ..., "status": ...}
    # **payload.model_dump()    -> title=..., status=...
    # Task(**...) then fills the ORM object's columns; we additionally
    # force owner_id = the authenticated user (never trust the client!).
    task = Task(**payload.model_dump(), owner_id=user.id)

    db.add(task)      # stage
    db.commit()       # INSERT + commit
    db.refresh(task)  # fetch generated id/created_at (+ category as a
                      # side effect for the response, thanks to lazy load)
    return task


# ---------------------------------------------------------------------
# READ ONE
# ---------------------------------------------------------------------
@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,               # FastAPI parses the URL path segment
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single task - but ONLY if it belongs to the current user."""
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
    """Update a task. Partial updates are allowed.

    PUT normally means "replace the whole resource", but with
    exclude_unset=True we turn this into a flexible PATCH-like endpoint:
    only the fields the client actually sent get applied.
    """

    task = _get_owned_task(db, task_id, user)

    # Same category ownership check as create (only when it was sent).
    if payload.category_id is not None:
        category = db.scalar(
            select(Category).where(
                Category.id == payload.category_id, Category.owner_id == user.id
            )
        )
        if category is None:
            raise HTTPException(status_code=400, detail="Invalid category_id")

    # model_dump(exclude_unset=True) -> ONLY the keys the client supplied.
    # setattr(task, field, value)    -> task.title = "...", etc.
    # The object is already tracked by the session, so the UPDATE is
    # emitted automatically on commit. No explicit UPDATE needed!
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    db.commit()      # runs UPDATE tasks SET ... WHERE id = ...
    db.refresh(task) # load refreshed row (incl. onupdate updated_at)
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
    """Delete a task. Returns 204 No Content (empty body) on success."""

    task = _get_owned_task(db, task_id, user)

    # Staged deletion -> emitted as DELETE on commit.
    db.delete(task)
    db.commit()
    # (A 204 response must not carry a body, so we return nothing and
    #  FastAPI sends an empty 204 for us.)


# ---------------------------------------------------------------------
# STATISTICS (a quick dashboard)
# ---------------------------------------------------------------------
@router.get("/stats/overview", response_model=TaskStats)
def task_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Count tasks by status/priority in as few queries as possible."""

    # AGGREGATION: one query, no Python loops.
    #
    #   base        = SELECT id, status, ... FROM tasks WHERE owner_id=?
    #                (materialized as a subquery)
    #   select(base.c.status, func.count()).group_by(base.c.status)
    #
    # generates   SELECT status, count(*) FROM (...) GROUP BY status
    #
    #   db.execute().all() -> list of (status_enum, count_int) pairs
    #   dict(...)          -> {PENDING: 2, COMPLETED: 1, ...}
    base = select(Task).where(Task.owner_id == user.id).subquery()
    status_counts = dict(
        db.execute(
            select(base.c.status, func.count()).group_by(base.c.status)
        ).all()
    )

    # Small closure doing the same aggregation for a concrete priority.
    def _priority_count(priority_value: TaskPriority) -> int:
        return db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.owner_id == user.id, Task.priority == priority_value)
        ) or 0

    # Assemble the response. `sum(status_counts.values())` avoids a
    # separate "count all" query; .get(key, 0) gives 0 when absent so a
    # brand-new user still sees sane zeros.
    return TaskStats(
        total=sum(status_counts.values()),
        pending=status_counts.get(TaskStatus.PENDING, 0),
        in_progress=status_counts.get(TaskStatus.IN_PROGRESS, 0),
        completed=status_counts.get(TaskStatus.COMPLETED, 0),
        high_priority=_priority_count(TaskPriority.HIGH),
        urgent_priority=_priority_count(TaskPriority.URGENT),
    )