# app/deps.py
# =====================================================================
# Shared FastAPI dependencies used across multiple routers.
# =====================================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models import User

# Tells FastAPI where to send the client if they try to call a protected
# route without a token. The login endpoint MUST match this URL.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the JWT from the Authorization header into a User.

    Steps:
      1. decode + verify the JWT (secret, algorithm, expiry)
      2. extract the `sub` claim (we stored the user id there)
      3. load that user from the database
    Raises 401 (credentials exception) on any failure.
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},  # required by OAuth2 spec
    )

    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_exception

    user_id = int(payload["sub"])

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    return user