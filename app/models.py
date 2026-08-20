# app/models.py
# =====================================================================
# SQLAlchemy ORM MODELS - Python classes that ARE database tables.
#
#   User      -> `users`      table   (login accounts)
#   Category  -> `categories` table   (labels for tasks, e.g. "Work")
#   Task      -> `tasks`      table   (the to-do items themselves)
#
# HOW THE MAGIC WORKS (declarative mapping):
#   At import time SQLAlchemy *inspects the class definition* and
#   derives a relational schema from it:
#
#     - which columns exist          -> from mapped_column(...)
#     - what SQL TYPE each column has -> from the `Mapped[type]` hint
#     - constraints / indexes / FKs   -> from the arguments
#     - table name                    -> __tablename__
#
#   Then it can:
#     1. CREATE TABLE  (via Base.metadata.create_all in main.py)
#     2. map rows <-> objects: a SELECT row becomes a `Task` instance.
#
# TYPE INFERENCE (SQLAlchemy 2.0 style):
#     Mapped[int]                    -> INTEGER (a primary key becomes SERIAL)
#     Mapped[str]                    -> VARCHAR (no length!)
#     Mapped[str] ... String(200)    -> VARCHAR(200)
#     Mapped[bool]                   -> BOOLEAN
#     Mapped[datetime]               -> DATETIME/TIMESTAMP
#     Mapped[date]                   -> DATE
#     Mapped[Optional[str]]          -> nullable column (NULL allowed)
#     Mapped[str]                    -> nullable=False (NOT NULL) implied!
#
# IMPORTANT: Optional[T] == nullable, plain T == NOT NULL. You get that
# for free just from the type hint - that's the 2.0 style's elegance.
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
# Inheriting from str as well as Enum makes each member also a string:
#     TaskStatus.PENDING == "pending"  ->  True
# That lets us use the enum directly inside JSON responses and SQL.
class TaskStatus(str, enum.Enum):
    """Where a task is in its lifecycle."""

    PENDING = "pending"          # created, not started
    IN_PROGRESS = "in_progress"  # actively being worked on
    COMPLETED = "completed"      # done


class TaskPriority(str, enum.Enum):
    """How important a task is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# sqlalchemy.Enum stores the enum MEMBER NAME ("PENDING") by default.
# We prefer lowercase values, so we teach it to store member.values: "pending".
def _enum_values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


# =====================================================================
# USER
# =====================================================================
class User(Base):
    """One row = one login account."""

    __tablename__ = "users"

    # primary_key=True -> part of the PRIMARY KEY (just one col here).
    # autoincrement=True -> for an integer PK this becomes SERIAL /
    #   GENERATED ALWAYS AS IDENTITY on PostgreSQL: the DB assigns ids.
    # unique=True adds a UNIQUE constraint - ids can never repeat.
    id: Mapped[int] = mapped_column(primary_key=True, unique=True)

    # unique=True, index=True on email and username:
    #   unique=True      -> no two users share an email/username
    #   index=True       -> build a B-tree so lookups by these columns
    #                       (our login query!) use the index instead of
    #                       scanning the whole table.
    # String(255) is the SET OF ALLOWED CHARS for PostgreSQL; think of it
    # as "max length".
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    # Optional[str] => nullable=True: a user may keep name empty (NULL).
    full_name: Mapped[Optional[str]] = mapped_column(String(150))

    # SECURITY: this column holds only the bcrypt HASH (from security.py).
    # Even the database never sees the plaintext password. If the DB ever
    # leaks, attackers get hashes, not passwords.
    hashed_password: Mapped[str] = mapped_column(String(255))

    # Soft-delete style flag: instead of removing rows we could set this
    # False. Keeps history, easy to restore.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # TIMESTAMP COLUMNS deserve their own deep-dive:
    #
    #   server_default=func.now()   -> baked into the CREATE TABLE DDL as
    #      `created_at TIMESTAMP WITH TIME ZONE DEFAULT now()`. The
    #      DATABASE sets the time. Why is that good? If the application
    #      sets it and crashes mid-insert, we already lost it. The DB
    #      setting it is atomic with the row.
    #
    #   DateTime(timezone=True)     -> TIMESTAMP WITH TIME ZONE on PG.
    #      Plain "now()" is fine here because PG stores UTC internally.
    #
    #   onupdate=func.now()         -> NOT in the DDL. This runs on the
    #      PYTHON side: whenever SQLAlchemy issues an UPDATE for the row,
    #      it adds `updated_at = now()` automatically.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # -----------------------------------------------------------------
    # RELATIONSHIPS (the heart of the ORM).
    #
    # relationship() is NOT a column - it creates no SQL. It tells
    # SQLAlchemy how to JOIN these tables, giving us conveniences:
    #
    #     user.tasks        -> list of the user's Task objects
    #     user.categories   -> list of the user's Category objects
    #
    # back_populates="owner"   joins TWO relationship()s on opposite ends
    # of the same foreign key, so both names work:
    #     user.tasks       (O2M: one user -> many tasks)
    #     task.owner       (M2O: one task -> its user)
    #
    # MERGING CONSTRAINT LEVELS:
    #   - Database layer:  Category.owner_id has ondelete="CASCADE", so
    #     DELETING a user row triggers PG to delete their categories.
    #   - ORM layer: cascade="all, delete-orphan" makes SQLAlchemy ALSO
    #     delete in-memory related objects so the two layers stay in sync
    #     (e.g. db.delete(user) + commit collects children itself).
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    categories: Mapped[List["Category"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    # __repr__ is purely for YOU while debugging in the console.
    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, email={self.email!r})>"


# =====================================================================
# CATEGORY
# =====================================================================
class Category(Base):
    __tablename__ = "categories"

    # __table_args__ lets us add constraints that span MULTIPLE columns.
    # This is a COMPOSITE UNIQUE INDEX on (owner_id, name):
    #   a user may not have two categories with the same name,
    #   while TWO DIFFERENT users CAN both have a "Work" category.
    __table_args__ = (
        Index("uq_category_owner_name", "owner_id", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))

    # 7 characters = one '#' + 6 hex digits, e.g. "#3b82f6". The client
    # chooses it; Pydantic validates the format (see schemas.py).
    color: Mapped[str] = mapped_column(String(7), default="#3b82f6")

    # -----------------------------------------------------------------
    # FOREIGN KEY = the relational join, defined at the DB level.
    #
    #     owner_id  ->  users.id
    #
    # ForeignKey("users.id", ondelete="CASCADE") means:
    #   - the value must exist in users.id (referential integrity) OR
    #     the DB rejects the insert
    #   - when the user row is DELETED, his categories are deleted too.
    # index=True -> frequent "WHERE owner_id = ?" lookups use an index.
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Both sides of the two relationships this table participates in:
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

    # Text (vs String) = unlimited length; used for long free-form text.
    description: Mapped[Optional[str]] = mapped_column(Text)

    # SQLAlchemy Enum for PostgreSQL creates a REAL database enum type:
    #
    #     CREATE TYPE task_status AS ENUM ('pending','in_progress',
    #                                       'completed')
    #
    # The DB itself then refuses anything that isn't a valid member -
    # a second line of defense on top of Pydantic. values_callable stores
    # lowercase VALUES rather than uppercase member names.
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", values_callable=_enum_values),
        default=TaskStatus.PENDING,   # Python-side default when inserting
        index=True,                   # fast WHERE status = ? filters
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, name="task_priority", values_callable=_enum_values),
        default=TaskPriority.MEDIUM,
        index=True,
    )

    # Date (not DateTime): just a calendar day, no time component.
    due_date: Mapped[Optional[date]] = mapped_column(Date)

    # SELF-DOCUMENTING FOREIGN KEYS:
    #
    #   category_id -> categories.id,  ondelete="SET NULL"
    #     If the category is deleted, tasks KEEP EXISTING and their
    #     category_id becomes NULL (they just lose their label).
    #     "SET NULL" requires the FK column to be nullable - it is.
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )

    #   owner_id -> users.id,  ondelete="CASCADE"
    #     Deleting a user removes ALL his tasks (no orphan rows).
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

    # Relationships again - note `Optional["Category"]`: a task may have
    # NO category, so accessing `task.category` can legitimately be None.
    owner: Mapped["User"] = relationship(back_populates="tasks")
    category: Mapped[Optional["Category"]] = relationship(back_populates="tasks")

    # LAZY LOADING note (useful to know while learning):
    # By default, `task.category` is NOT fetched in the initial SELECT
    # for the task. It fires a SECOND query the first time you access it.
    # For simple apps that's fine. When rows get numerous you'd switch to
    # eager loading (selectinload/joinedload) to avoid N+1 queries.
    def __repr__(self) -> str:
        return f"<Task(id={self.id!r}, title={self.title!r}, status={self.status!r})>"