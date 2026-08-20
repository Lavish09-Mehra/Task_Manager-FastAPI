# app/routers/auth.py
# =====================================================================
# Authentication endpoints:
#   POST /auth/register   -> create a new user account
#   POST /auth/login      -> exchange username+password for a JWT
#   GET  /auth/me         -> return the currently logged-in user
# =====================================================================

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Create a new user account and return its public data."""

    # catch duplicates: same email OR same username already taken
    existing = db.scalar(
        select(User).where(or_(User.email == payload.email, User.username == payload.username))
    )
    if existing:
        # 409 Conflict - tell the client which field collided
        field = "email" if existing.email == payload.email else "username"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{field} already registered",
        )

    # Only ever store the bcrypt HASH, never the plaintext password.
    user = User(
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)  # reload to get id / created_at from the DB
    return user


@router.post("/login", response_model=Token)
def login(
    # OAuth2PasswordRequestForm = standard `application/x-www-form-urlencoded`
    # body with `username` and `password` fields.
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Log in with username/email + password and receive an access token.

    The returned token must be sent as:
        Authorization: Bearer <access_token>
    """

    user = db.scalar(
        select(User).where(
            or_(User.username == form_data.username, User.email == form_data.username)
        )
    )

    # Same error for "unknown user" and "wrong password" on purpose so we
    # don't reveal which usernames exist.
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # The `sub` (subject) claim stores the user id. On future requests we
    # read it back to find the user - no server-side session needed.
    token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the authenticated user."""
    return current_user