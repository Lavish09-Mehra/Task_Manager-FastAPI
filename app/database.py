# app/database.py
# =====================================================================
# SQLAlchemy SETUP - the foundation of everything database-related.
#
# Every SQLAlchemy application is built from three core objects:
#
#   ┌────────────────────────────────────────────────────────────────┐
#   │  1. ENGINE       A "connection pool". It knows HOW to talk to    │
#   │                  the database (which driver, what URL) and keeps │
#   │                  a handful of live DB connections open so we     │
#   │                  don't pay the TCP + handshake cost per request. │
#   │                                                                  │
#   │  2. SessionLocal EVERY request gets a brand new Session from a   │
#   │                  lightweight factory (never share sessions!)      │
#   │                                                                  │
#   │  3. Base         The registry. Every ORM model inherits Base,    │
#   │                  and SQLAlchemy collects each model's metadata   │
#   │                  so it can CREATE/DROP tables and map rows.      │
#   └──────────────────────────────────────────────────────────────────┘
#
# It also defines `get_db`, the FastAPI dependency that hands each HTTP
# request a fresh database Session and guarantees it gets closed.
# =====================================================================

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


# ---------------------------------------------------------------------
# 1) ENGINE
# ---------------------------------------------------------------------
# create_engine(URL) reads the URL, picks the right DBAPI driver
# (here "postgresql+psycopg2://") and builds a pool of connections.
#
#   echo=True (from DEBUG) -> logs EVERY SQL statement to the console.
#     The line after each request shows what our Python produced:
#       2026-... INFO sqlalchemy.engine.Engine SELECT users.id AS ...
#     This is THE best way to learn what SQL your ORM code generates.
#
#   pool_pre_ping=True -> before handing out a pooled connection, run a
#     tiny "SELECT 1" to check it's still alive. A DB restart would
#     otherwise leave stale connections in the pool that fail later
#     with confusing "connection already closed" errors.
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# ---------------------------------------------------------------------
# 2) SESSION FACTORY
# ---------------------------------------------------------------------
# SessionLocal() gives us a fresh Session = ONE "unit of work":
#
#   db = SessionLocal()      # start a conversation with the DB
#   db.add(task)             # stage an object (nothing sent yet!)
#   db.commit()              # flush INSERT/UPDATEs + end transaction
#   db.rollback()            # undo everything since the last commit
#   db.close()               # return the connection to the pool
#
# Why autocommit=False ?  SQLAlchemy wraps work in transactions, and we
# want to be IN CONTROL of when data hits the disk. Nothing is saved
# until we explicitly call commit().
#
# Why autoflush=False ?  By default SQLAlchemy silently runs pending
# INSERT/UPDATE statements before some queries. Disabling it makes the
# behavior explicit and predictable while learning.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ---------------------------------------------------------------------
# 3) DECLARATIVE BASE
# ---------------------------------------------------------------------
# Every model (models.py) subclasses Base. SQLAlchemy inspects the
# *class* (not instances) - it reads attributes/type hints/column
# definitions and builds:
#   - a Table object per model   -> used to issue CREATE TABLE
#   - a mapper per model         -> used to map rows <-> Python objects
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------
# 4) get_db FastAPI dependency
# ---------------------------------------------------------------------
# FastAPI dependencies are functions whose result is injected into the
# route. By writing `db: Session = Depends(get_db)` in a route we get:
#
#   1. this function runs  -> creates the Session
#   2. its `yield db`      -> FastAPI injects `db` into the route
#   3. route finishes      -> FastAPI resumes right after the yield
#                            (with Next OrderedDependency etc.)
#   4. `finally: db.close()`-> connection returns to the pool.
#
# The `finally` block is the important part: it runs even if the route
# raised an exception, so we never leak connections on errors.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()