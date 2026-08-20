# app/core/security.py
# =====================================================================
# Helpers for password hashing and JWT (JSON Web Token) creation/decoding.
#
#   bcrypt      -> irreversible password hashing (never store plaintext!)
#   PyJWT       -> creates signed tokens so the API "remembers" a user
#                  without storing any session state server-side.
# =====================================================================

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt

from app.core.config import settings


# ---------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Hash a plaintext password into a bcrypt hash string.

    bcrypt automatically adds a random 'salt' (gensalt), so two users
    with the same password get DIFFERENT hashes. We never store plaintext.
    """
    # encode str -> bytes, hash with a salt, decode bytes -> str for storage
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ---------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------
def create_access_token(data: dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    """Create a signed JWT containing the given data.

    The token also gets an `exp` (expiry) claim so it cannot be used
    forever if leaked. Signed with SECRET_KEY -> cannot be forged.
    """
    to_encode = data.copy()
    # Default expiry from settings, or a custom value if provided.
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """Decode + verify a JWT. Returns the payload, or None if invalid/expired.

    Composition of the token secret/algorithm is checked *and* `exp` is
    validated automatically by PyJWT.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except jwt.PyJWTError:
        # invalid signature, expired token, malformed token, ...
        return None