# app/core/config.py
# =====================================================================
# Central configuration for the whole application.
#
# We use `pydantic-settings`, which reads values from environment
# variables AND from the .env file located at the project root.
#
#   .env (NOT committed to git)    -> actual secrets
#   .env.example (committed)       -> placeholder template for others
# =====================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Each annotated attribute is read from the environment / .env.
    Pydantic validates the values (types, required fields, etc.).
    """

    # --- App metadata -------------------------------------------------
    PROJECT_NAME: str = "Task Manager API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"  # all routes live under this prefix

    # --- Security / JWT ----------------------------------------------
    SECRET_KEY: str         # NO default: must exist in .env!
    ALGORITHM: str = "HS256"  # JWT signing algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # --- Database ------------------------------------------------------
    #  format: dialect+driver://user:password@host:port/database
    DATABASE_URL: str

    # Prints every SQL statement when True - great for learning,
    # turn OFF in production.
    DEBUG: bool = True

    # Tell pydantic-settings to load key=value pairs from .env.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# A single shared instance imported everywhere:
#   from app.core.config import settings
settings = Settings()