# app/deps.py
# =====================================================================
# SHARED FASTAPI DEPENDENCIES.
#
# Dependencies are just functions that FastAPI runs and then injects into
# your route's arguments. You can stack them: a route depends on
# `get_current_user`, which itself depends on `oauth2_scheme` and
# `get_db`. FastAPI resolves the whole chain automatically.
#
# Request flow for a protected route (e.g. GET /api/v1/tasks):
#
#   Client sends:  GET /api/v1/tasks
#                  Authorization: Bearer eyJhbG...
#
#   oauth2_scheme     -> checks header exists, extracts the token string
#                        (raises 401 if no / malformed Authorization)
#   get_db            -> opens a Session
#   get_current_user  -> decode JWT -> find user -> return it
#   list_tasks(...)   -> gets `user` and `db`, does the query
#   get_db resumes    -> closes the Session in its `finally`
# =====================================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models import User

# ---------------------------------------------------------------------
# OAuth2PasswordBearer is a FastAPI "security scheme". Two jobs:
#   1. At startup it documents our security in the /docs schema:
#      "This endpoint expects a bearer token".
#   2. Per request it reads the HTTP header `Authorization: Bearer <t>`
#      and returns the token string (or raises 401).
#
# tokenUrl points at our login route - used by the docs' "Authorize"
# button so you can paste a token for a clean testing experience.
# The string MUST match the actual login route we mount in main.py
# (prefix "/api/v1" + router prefix "/auth" + path "/login").
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Reconstruct who is calling from the JWT, or refuse the request.

    Steps (each FAILURE ends the request with 401):
      1. `token` was already extracted by oauth2_scheme.
      2. decode_access_token verifies signature + expiry and returns the
         payload (a dict of claims). None means "not a valid token".
      3. We look up the `sub` claim - the user id we baked in at login.
      4. db.get(User, user_id) fetches that row by primary key.
      5. If the user was deleted (or deactivated) meanwhile -> 401.

    NOTE: this runs BEFORE the route handler thanks to `Depends`, so the
    route code can just trust the `user` argument it receives.
    """

    # A helper exception with exactly the shape the OAuth2 spec expects.
    # The WWW-Authenticate response header tells clients "you need a
    # valid Bearer token to retry".
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_exception

    # The sub claim was stored as a str in security.py - convert it back.
    user_id = int(payload["sub"])

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    return user