# app/schemas.py
# =====================================================================
# PYDANTIC SCHEMAS = "DTOs" (Data Transfer Objects).
#
# The single most important idea in a FastAPI + SQLAlchemy app:
#
#   ORM model (models.py)  <->  talks to the DATABASE
#   Pydantic schema        <->  talks to the CLIENT (HTTP/JSON)
#
# They look similar but are two totally different worlds:
#   - SQLAlchemy models are mutable Python objects tracked by a Session.
#   - Pydantic models validate and *serialize* plain data.
#
# Why not just expose ORM objects straight to the client?
#   1. SAFETY  - you only expose the exact fields you choose.
#                (e.g. UserOut has NO hashed_password!)
#   2. CONTROL - request bodies come pre-validated: wrong types, missing
#                fields, too-short passwords... rejected before your
#                route code ever runs, returning 422 to the client.
#   3. VERSION - you can change DB internals without changing the API.
#
# HOW IT WORKS under a request:
#   POST /tasks
#     body -> TaskCreate(...)   (Pydantic parses + validates JSON)
#     task = Task(**payload.model_dump())   (pass to the ORM)
#     return task               (FastAPI runs TaskOut.validate_python(task))
# =====================================================================

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import TaskPriority, TaskStatus

# NOTE about importing from models.py: the enum VALUES live in one place
# (models.py) so the API and the database can never drift apart. We are
# NOT coupling to the ORM classes, just reusing the enum members.


# =====================================================================
# AUTH / USER schemas
# =====================================================================
class UserCreate(BaseModel):
    """Request body for POST /auth/register.

    This is a "Create" schema: it describes what the CLIENT must send.
    """
    # EmailStr is a pydantic type that REQUIRES the `email-validator`
    # package and validates the address format: 'a@b' fails, correct ones
    # pass. No more sloppy email handling by hand.
    email: EmailStr

    # Field(..., ...) -> first argument is the DEFAULT value.
    #   "..." (Ellipsis) means "no default, this field is REQUIRED".
    # Even if someone omits password, min_length etc. reject it with a
    # readable error message.
    username: str = Field(
        ...,
        min_length=3,     # must be at least 3 characters
        max_length=50,    # at most 50
        pattern=r"^[a-zA-Z0-9_]+$",  # only letters, digits, underscore
    )
    full_name: Optional[str] = Field(None, max_length=150)  # optional
    password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    """What the API RETURNS about a user.

    Deliberately has NO password field - even a hash must never leak out
    of the API. Notice there's no hashed_password attribute here at all.
    """

    # from_attributes=True lets Pydantic build this schema straight from a
    # SQLAlchemy User object by reading its attributes (user.id, ...),
    # instead of only accepting JSON dicts.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    """Response of a successful login: the JWT bearer token."""

    access_token: str             # the JWT string from security.py
    token_type: str = "bearer"    # how the client must present it


# =====================================================================
# CATEGORY schemas
# =====================================================================
class CategoryCreate(BaseModel):
    """What the client must send to create a category."""
    # Field(...) again means "required, no default".
    name: str = Field(..., min_length=1, max_length=100)
    # A HEX COLOR such as "#3b82f6". The regex validates the format,
    # so "red" or "blue" get rejected with an automatic 422.
    color: str = Field("#3b82f6", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        """FIELD VALIDATOR - runs automatically AFTER type validation.

        Here we normalize the name so " Work " and "Work" are treated as
        the same category by the database unique-guard in categories.py.
        Pydantic calls this AFTER the built-in checks pass and uses the
        RETURNED value as the final field value.
        Need `@classmethod` by design - raise ValueError to reject.
        """
        v = v.strip()
        if not v:                    # a name of only spaces == empty
            raise ValueError("category name cannot be empty")
        return v


class CategoryUpdate(BaseModel):
    """Update schema: EVERY field is Optional on purpose.

    This is what makes the PUT endpoint a "partial update" - the client
    can send just {"color": "#000000"} and the name stays untouched
    (the router applies only the fields that were actually sent).
    """
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class CategoryOut(BaseModel):
    """Response schema for a category."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    created_at: datetime


# =====================================================================
# TASK schemas
# =====================================================================
class CategoryRef(BaseModel):
    """A SMALL slice of a Category, nested inside a Task response.

    Instead of returning a full Category object (with its own created_at,
    owner_id...) we expose just the useful trio. This is what "DTO"
    design is about: each API shape is tailored to its use.
    """

    # Pydantic v2 gotcha: `from_attributes` does NOT cascade down to
    # nested models automatically. TaskOut may be from_attributes, but
    # its child CategoryRef needs its own config - otherwise Pydantic
    # can't convert a SQLAlchemy Category instance and raises a
    # "model_type" validation error. (We hit this exact bug while
    # testing!)
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str


class TaskCreate(BaseModel):
    """Request body for POST /tasks."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    # Reusing the ORM enum class gives us free validation: the client can
    # only send "pending" | "in_progress" | "completed" - anything else
    # is rejected with 422. Same guarantees at DB level AND at API level.
    status: TaskStatus = TaskStatus.PENDING          # default if omitted
    priority: TaskPriority = TaskPriority.MEDIUM    # default if omitted
    due_date: Optional[date] = None                 # e.g. "2026-09-01"
    category_id: Optional[int] = None               # FK, validated later

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v


class TaskUpdate(BaseModel):
    """Partial update body - same trick as CategoryUpdate."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None
    category_id: Optional[int] = None


class TaskOut(BaseModel):
    """Response schema for a task.

    Matches the Task model but shapes it for the client:
      - nests a `category` object (if any) instead of a raw category_id
      - includes timestamps
      - and, crucially, includes NO `owner_id` - other users must not
        learn who owns a task.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str]
    status: TaskStatus                  # serialized as string value
    priority: TaskPriority              # e.g. "high", not "HIGH"
    due_date: Optional[date]
    category: Optional[CategoryRef] = None   # populated via the ORM relation
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    """PAGINATION WRAPPER - the list endpoint returns this, not a bare
    list. Metadata (total/page/size) lets a UI render a proper pager."""

    total: int          # how many rows MATCHED the filters (before slicing)
    page: int           # current page number, 1-based
    size: int           # how many items were requested per page
    items: List[TaskOut]  # the slice of items for THIS page


class TaskStats(BaseModel):
    """Dashboard numbers returned by /tasks/stats/overview."""

    total: int
    pending: int
    in_progress: int
    completed: int
    high_priority: int
    urgent_priority: int