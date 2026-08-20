# app/schemas.py
# =====================================================================
# PYDANTIC SCHEMAS (DTOs - Data Transfer Objects).
#
# These are NOT the SQLAlchemy models. They validate/serialize data that
# crosses the HTTP boundary:
#   * request bodies  -> validated before your route code runs
#   * response bodies -> serialized to clean JSON
#
# `ConfigDict(from_attributes=True)` lets Pydantic build a schema
# directly from an ORM object (e.g. return a SQLAlchemy Task).
# =====================================================================

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import TaskPriority, TaskStatus


# =====================================================================
# AUTH / USER schemas
# =====================================================================
class UserCreate(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr                       # validated format: foo@bar.com
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    full_name: Optional[str] = Field(None, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    """What the API returns about a user - note: NO password ever!"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    """Response of a successful login - the JWT access token."""

    access_token: str
    token_type: str = "bearer"


# =====================================================================
# CATEGORY schemas
# =====================================================================
class CategoryCreate(BaseModel):
    # "..." means required. Colour validated as a hex colour.
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field("#3b82f6", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        """Trim whitespace so ' Work ' and 'Work' are not different."""
        v = v.strip()
        if not v:
            raise ValueError("category name cannot be empty")
        return v


class CategoryUpdate(BaseModel):
    """Partial update -> every field optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    created_at: datetime


# =====================================================================
# TASK schemas
# =====================================================================
class CategoryRef(BaseModel):
    """Small nested category object included inside a Task response."""

    # `from_attributes` must be set HERE too - in Pydantic v2 it does NOT
    # automatically inherit from the parent model (TaskOut).
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    status: TaskStatus = TaskStatus.PENDING          # reuses the ORM enum
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[date] = None
    category_id: Optional[int] = None                # must exist when set!

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v


class TaskUpdate(BaseModel):
    """Partial update endpoint -> all fields optional."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None
    category_id: Optional[int] = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[date]
    category: Optional[CategoryRef] = None   # nested category info
    created_at: datetime
    updated_at: datetime


# Paginated list response (wraps results + metadata).
class TaskPage(BaseModel):
    total: int          # how many tasks matched the filters
    page: int           # current page (1-based)
    size: int           # items per page
    items: List[TaskOut]


# Simple statistics endpoint response.
class TaskStats(BaseModel):
    total: int
    pending: int
    in_progress: int
    completed: int
    high_priority: int
    urgent_priority: int