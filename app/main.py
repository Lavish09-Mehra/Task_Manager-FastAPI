# app/main.py
# =====================================================================
# THE APPLICATION ENTRY POINT.
#
# This module is what uvicorn loads:
#
#     uvicorn app.main:app --reload
#             ^     ^       ^
#             |     |       +-- auto-reload on file changes (dev only)
#             |     +---------- the `app` object defined below
#             +---------------- import path: the file app/main.py
#
# It is the "composition root": it imports / wires together every part:
#   - creates the FastAPI() instance
#   - builds all tables at startup (learning shortcut)
#   - mounts the three routers under the /api/v1 prefix
#
# After starting, open:   http://127.0.0.1:8000/docs
#   -> interactive Swagger UI, generated automatically from the code
#      (route signatures + Pydantic schemas + security scheme).
# =====================================================================

from fastapi import FastAPI

from app.core.config import settings
from app.database import Base, engine
from app.routers import auth, categories, tasks

# ---------------------------------------------------------------------
# TABLE CREATION ON STARTUP.
#
# When this module is imported:
#   - models.py gets imported (indirectly via the routers) and therefore
#     every model class REGISTERS itself on Base.metadata.
#   - create_all() then issues CREATE TABLE IF NOT EXISTS for each of
#     those tables, plus the PostgreSQL ENUM types.
#
# NOTE FOR LEARNING: create_all only CREATES missing tables. It does NOT
# alter or drop anything - if you change a column, your table won't
# change. That's exactly why production projects switch to ALEMBIC
# migrations (versioned, incremental schema changes).
# ---------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

# The FastAPI instance. `title`/`description`/`version` appear in the
# generated docs and in the OpenAPI schema that tools can consume.
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "A full Task Manager API built with FastAPI + SQLAlchemy. "
        "Register an account, then use the returned token on every request."
    ),
    version=settings.VERSION,
)

# ---------------------------------------------------------------------
# MOUNTING ROUTERS (why the URLs look like /api/v1/...)
#
# Each router declares its OWN prefix ("/auth", "/tasks", "/categories").
# include_router(prefix=...) adds a global prefix on top, so the final
# paths become:
#
#   /api/v1/auth        + /register|/login|/me
#   /api/v1/tasks       + CRUD + /stats/overview
#   /api/v1/categories  + CRUD
#
# The versioned prefix is a common REST convention so you can later break
# the API (v2) without breaking existing clients.
# ---------------------------------------------------------------------
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(tasks.router, prefix=settings.API_V1_PREFIX)
app.include_router(categories.router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["meta"])
def root():
    """Friendly landing page pointing people to the docs."""
    return {
        "message": "Welcome to the Task Manager API",
        "docs": "/docs",              # interactive Swagger UI
        "version": settings.VERSION,
    }