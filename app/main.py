# app/main.py
# =====================================================================
# Entry point of the FastAPI application.
#
# Run it:        uvicorn app.main:app --reload
# API docs:      http://127.0.0.1:8000/docs
# =====================================================================

from fastapi import FastAPI

from app.core.config import settings
from app.database import Base, engine
from app.routers import auth, categories, tasks

# ---------------------------------------------------------------------
# Create all tables on startup.
# (Good enough for a learning project; a real deployment would use
#  Alembic migrations so the schema can evolve safely.)
# ---------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "A full Task Manager API built with FastAPI + SQLAlchemy. "
        "Register an account, then use the returned token on every request."
    ),
    version=settings.VERSION,
)

# Mount every router under the versioned prefix, e.g.
#   fastapi /api/v1/auth/login      /api/v1/tasks     /api/v1/categories
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(tasks.router, prefix=settings.API_V1_PREFIX)
app.include_router(categories.router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["meta"])
def root():
    """Friendly root endpoint pointing people to the docs."""
    return {
        "message": "Welcome to the Task Manager API",
        "docs": "/docs",
        "version": settings.VERSION,
    }