# app/database.py
# =====================================================================
# SQLAlchemy setup: the three pieces every app needs ->
#
#   1. ENGINE      - how to connect (driver + connection pool)
#   2. SessionLocal- a factory that creates one "unit of work" session
#   3. Base        - every ORM model inherits from this
#
# Also provides `get_db`, the FastAPI dependency used by routers to get
# a database session for each HTTP request.
# =====================================================================

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------
# 1) ENGINE
# ---------------------------------------------------------------------
# create_engine builds a connection pool to the database.
#   echo=True       -> print every SQL statement (learning!)
#   pool_pre_ping   -> test a connection before use (avoids stale conns)
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# ---------------------------------------------------------------------
# 2) SESSION FACTORY
# ---------------------------------------------------------------------
# Call SessionLocal() to get a new Session:
#   autocommit=False -> nothing is saved until you call commit()
#   autoflush=False  -> queries don't silently push pending changes
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ---------------------------------------------------------------------
# 3) DECLARATIVE BASE
# ---------------------------------------------------------------------
class Base(DeclarativeBase):
    """All ORM models inherit from Base so SQLAlchemy can map tables."""


# ---------------------------------------------------------------------
# 4) get_db dependency
# ---------------------------------------------------------------------
def get_db():
    """FastAPI dependency: open a Session per request, always clean up.

    Usage in routes:      db: Session = Depends(get_db)
    The `finally` guarantees .close() runs even if an error is raised,
    so connections are never leaked.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()