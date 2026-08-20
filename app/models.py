# app/models.py
# =====================================================================
# SQLAlchemy ORM MODELS -> Python classes mapped to database tables.
#
#   User      -> the `users` table      (login accounts)
#   Category  -> the `categories` table (group tasks, e.g. "Work")
#   Task      -> the `tasks` table      (the actual to-do items)
#
# Modern SQLAlchemy 2.0 style: columns declared via type hints
#   attribute: Mapped[type] = mapped_column(...)
#
# NOTE: enum classes defined here are reused by Pydantic schemas so the
# values are ALWAYS in sync between the DB and the API.
# =====================================================================

import enum
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# =====================================================================
# ENUMS (shared vocabulary for status / priority)
# =====================================================================
class TaskStatus(str, enum.Enum):
    """Where a task is in its lifecycle."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskPriority(str, enum.Enum):
    """How important a task is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# Helper: store the *value* of our enums (e.g. "pending" not "PENDING")
# in the database column.
def _enum_values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


# =====================================================================
# USER
# =====================================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # unique=True + index=True -> fast lookups by email during login
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(150))

    # NEVER store a plaintext password - only the bcrypt hash.
    hashed_password: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # server_default -> the DATABASE sets the timestamp, so it is
    # reliable even if the app crashes between insert and commit.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),  # auto-refresh this column on UPDATE
    )

    # Relationships (they don't create columns; they give us conveniences):
    #   user.tasks      -> all Task rows with owner_id == this user
    #   user.categories -> all Category rows owned by this user
    # cascade="all, delete-orphan" -> deleting a user deletes their data too
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    categories: Mapped[List["Category"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, email={self.email!r})>"


# =====================================================================
# CATEGORY
# =====================================================================
class Category(Base):
    __tablename__ = "categories"
    # A user can have many categories -> owner_id is a UNIQUE constraint
    # on (owner_id, name) so a user cannot create duplicate category names.
    __table_args__ = (
        Index("uq_category_owner_name", "owner_id", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    # Optional 7-char hex colour like "#3b82f6" for nicer UIs.
    color: Mapped[str] = mapped_column(String(7), default="#3b82f6")

    # ForeignKey("users.id") links this row to the owning user.
    # ondelete="CASCADE" -> if the user is deleted, their categories vanish.
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="categories")
    tasks: Mapped[List["Task"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"<Category(id={self.id!r}, name={self.name!r})>"


# =====================================================================
# TASK
# =====================================================================
class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)  # TEXT = long text

    # SQLAlchemy Enum -> creates a PostgreSQL ENUM type automatically.
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", values_callable=_enum_values),
        default=TaskStatus.PENDING,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority", values_callable=_enum_values),
        default=TaskPriority.MEDIUM,
        index=True,
    )

    due_date: Mapped[Optional[date]] = mapped_column(Date)  # just a DATE, no time

    # Optional link to a Category. ondelete="SET NULL" => if the category
    # is deleted, the task is kept but its category becomes NULL.
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )

    # Every task belongs to exactly one user (the owner).
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner: Mapped["User"] = relationship(back_populates="tasks")
    category: Mapped[Optional["Category"]] = relationship(back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task(id={self.id!r}, title={self.title!r}, status={self.status!r})>"