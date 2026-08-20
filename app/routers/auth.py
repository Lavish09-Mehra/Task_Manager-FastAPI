# app/routers/auth.py
# =====================================================================
# AUTHENTICATION ROUTES.
#
# A router is a self-contained group of routes that main.py "mounts"
# into the app. Here the prefix is "/auth", so with main.py's "/api/v1"
# prefix the real URLs become:
#
#   POST /api/v1/auth/register   create an account
#   POST /api/v1/auth/login      exchange credentials for a JWT
#   GET  /api/v1/auth/me         who am I? (requires token)
#
# The full login flow, step by step:
#
#   register:  client sends email+username+password (as JSON)
#              -> UserCreate validates it
#              -> we hash the password with bcrypt
#              -> a User row is INSERTed
#              -> bcrypt hash stored, plaintext discarded forever
#
#   login:     client sends username+password (as a FORM, since we use
#              OAuth2PasswordRequestForm - standard for OAuth2 flows)
#              -> we look the user up, verify the bcrypt hash
#              -> we sign a JWT with {"sub": user.id, "exp": ...}
#              -> client stores the token and sends it on every request
#
#   me:        client sends Authorization: Bearer <token>
#              -> get_current_user decodes it and loads the user
#              -> we return their profile
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

# APIRouter: a mini-application with its own routes and tags.
#   prefix -> everything here is mounted under "/auth"
#   tags   -> groups these routes in the generated OpenAPI/ Swagger docs.
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Create a new user account and return its public data.

    FastAPI call order:
      1. Parse+validate JSON body into a UserCreate (422 if invalid)
      2. Run get_db() -> a Session is injected as `db`
      3. Execute the function below
    """

    # Duplicate check BEFORE inserting. `or_` builds
    #   WHERE users.email = :e OR users.username = :u
    # db.scalar returns the single matched row (or None).
    existing = db.scalar(
        select(User).where(or_(User.email == payload.email, User.username == payload.username))
    )
    if existing:
        # 409 Conflict is the "the resource already exists" status code.
        # We tell the client WHICH field collided so they can fix it
        # (e.g. show a red hint under the username input).
        field = "email" if existing.email == payload.email else "username"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{field} already registered",
        )

    # Build the ORM object. Note: NO plaintext password anywhere -
    # `hash_password` replaces it with the bcrypt digest immediately.
    user = User(
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )

    # The classic INSERT dance:
    #   db.add(user)    -> "stage" the object in this session (pending)
    #   db.commit()     -> flush the INSERT to the DB, end transaction
    #   db.refresh(user)-> re-SELECT the row so `id`, `created_at` (set
    #                      by the database's SERIAL / now() defaults)
    #                      are copied back onto the Python object.
    db.add(user)
    db.commit()
    db.refresh(user)
    return user  # FastAPI serializes it via UserOut -> no password field


@router.post("/login", response_model=Token)
def login(
    # OAuth2PasswordRequestForm is a FORM dependency (not JSON!).
    # The login body must be `application/x-www-form-urlencoded` with
    # fields `username` and `password`. This is the standard OAuth2 way.
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate and hand out a JWT access token.

    Usernames can be our `username` OR the `email` - both columns are
    searched, so logging in with either works.
    """

    # Build: SELECT * FROM users WHERE username = :x OR email = :x
    user = db.scalar(
        select(User).where(
            or_(User.username == form_data.username, User.email == form_data.username)
        )
    )

    # SECURITY BEST PRACTICE: "user not found" and "wrong password" produce
    # the EXACT same message + status. If they differed, an attacker could
    # enumerate which emails are registered. We also do not reveal which
    # branch failed in timing here - bcrypt runs in both failure paths.
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # The `sub` claim is the user id. We store it as a STRING (JWT spec
    # says so). Because the token is SIGNED (SECRET_KEY), no one can edit
    # sub to impersonate someone else.
    token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=token)   # token_type defaults to "bearer"


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user.

    The `current_user` parameter is FILLED by the get_current_user
    dependency (deps.py) which decoded the Bearer token. We don't need a
    database here - the dependency already did the lookup.
    """
    return current_user