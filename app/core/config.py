# app/core/config.py
# =====================================================================
# CENTRAL CONFIGURATION (a.k.a. "12-factor config").
#
# The golden rule: NEVER hard-code configuration inside your code.
# Things like the database URL, secret keys, environment name, etc. have
# to be swappable between your laptop, a staging server and production.
#
# `pydantic-settings` is a small library that:
#   1. reads the .env file (project root) into key/value pairs
#   2. reads real OS environment variables too
#   3. maps them onto the typed attributes below via NAME MATCHING,
#      and *validates* each value (str/int/bool checks happen here!)
#
# Real environment variables take precedence over .env values.
# =====================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every annotated attribute is looked up by NAME in the env/.env.

    Example: `DATABASE_URL: str` will be filled from the environment
    variable `DATABASE_URL`. If it's missing -> pydantic raises an error
    *at import time*, so misconfiguration fails fast, not at runtime.

    Attributes WITHOUT a default VALUE are REQUIRED.
    """

    # --- App metadata -------------------------------------------------
    PROJECT_NAME: str = "Task Manager API"   # shown in the Swagger docs
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"           # every router is mounted here

    # --- Security / JWT ----------------------------------------------
    # REQUIRED - it is the secret that signs our tokens. It is purposefully
    # given NO default, so the app refuses to start without it.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"                 # symmetric-key JWT algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h before token expires

    # --- Database -----------------------------------------------------
    # REQUIRED. Format:
    #     dialect+driver://username:password@host:port/database
    # e.g. postgresql+psycopg2://postgres:secret@localhost:5432/taskdb
    DATABASE_URL: str

    # When True, SQLAlchemy prints every SQL statement (great for learning,
    # too noisy for production).
    DEBUG: bool = True

    # Where and HOW to load the values: from the file ".env" located in
    # the current working directory, encoded as UTF-8.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# A single shared instance. Because it's created once at module import,
# the .env is parsed exactly ONCE per process.
#   from app.core.config import settings   ->  settings.DATABASE_URL
settings = Settings()