# app/core/security.py
# =====================================================================
# SECURITY PRIMITIVES used by the auth router:
#
#   bcrypt   -> one-way password hashing   (the user's password secret)
#   PyJWT    -> signed stateless tokens    (the "who am I" secret)
#
# BOTH secrets have a story worth understanding:
#
# ┌──────────────────────────── PASSWORD HASHING ─────────────────────────┐
# │  Storing passwords "in plain text" is catastrophic: if the database    │
# │  leaks, every password leaks. So we store a HASH instead.              │
# │                                                                        │
# │  bcrypt.hashpw(password, gensalt):                                     │
# │    1. gensalt()  generates ~16 random bytes (the "salt")               │
# │    2. the hash algorithm mixes salt + password MANY rounds, so that    │
# │       brute-forcing one hash costs seconds of CPU, not microseconds    │
# │    3. the output LOOKS like:  $2b$12$<22-char salt><31-char hash>      │
# │                                                                        │
# │  Random salt means: the SAME password hashed twice gives DIFFERENT     │
# │  strings. Attackers can't use pre-computed "rainbow tables".           │
# │  (The salt is stored INSIDE the hash string itself, so verification    │
# │   doesn't need a separate salt column.)                                │
# └────────────────────────────────────────────────────────────────────────┘
# ┌──────────────────────────────── JWTs ─────────────────────────────────┐
# │  A JWT is 3 base64 blobs joined by dots:  header.payload.signature    │
# │     header    { "alg": "HS256", "typ": "JWT" }                        │
# │     payload   { "sub": "5", "exp": 1789..., "iat": ... }  -> claims  │
# │     signature HMAC-SHA256(header.payload, SECRET_KEY)                 │
# │                                                                       │
# │  Anyone can READ the payload (it is NOT encrypted!), but they CANNOT  │
# │  forge one, because they don't know SECRET_KEY. The server verifies   │
# │  the signature on every request and trusts whatever's inside.         │
# │  This is "stateless auth": no session stored server-side.             │
# └──────────────────────────────────────────────────────────────────────┘
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

    HOW TO READ THE RESULT: "$2b$12$<salt+hash>"
        $2b$   -> bcrypt algorithm version
        12     -> cost factor (2^12 = 4096 rounds). Higher = slower = safer.
        rest   -> salt (22 chars) + digest (31 chars), all in base64.
    """
    # bcrypt works on BYTES, not str, hence .encode("utf-8").
    # .decode("utf-8") turns the bytes result back into a string so we can
    # store it in a VARCHAR column.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare a candidate password against a stored bcrypt hash.

    bcrypt.checkpw:
      1. reads the salt OUT of the stored hash string
      2. re-hashes the candidate with that same salt
      3. compares both digests using a CONSTANT-TIME comparison, so that a
         fast attacker (measuring response times) can't tell how many
         characters already matched. Small but real security detail.
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ---------------------------------------------------------------------
# JWT creation / decoding
# ---------------------------------------------------------------------
def create_access_token(data: dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    """Create a signed JWT carrying the given claims.

    We always attach an `exp` (expiration) claim, so a stolen token stops
    working after a while instead of being valid forever.
    """
    to_encode = data.copy()  # never mutate the caller's dict

    # Expiry = now + configured lifetime (or a custom one, if passed).
    # Note: we use timezone-aware UTC times - always compare apples to
    # apples when dealing with instants in time.
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})

    # jwt.encode simply performs the header.payload.signature dance from
    # the ASCII diagram above, using our SECRET_KEY.
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """Verify a JWT and return its payload, or None if it's not usable.

    PyJWT verifies the SIGNATURE using SECRET_KEY (proves we issued it)
    and checks the `exp` claim (proves it hasn't expired). Any tampering,
    bad signature or expiry -> jwt.PyJWTError -> we return None and the
    caller turns that into an HTTP 401.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],  # must be explicitly listed
        )
    except jwt.PyJWTError:
        # invalid signature, expired token, malformed token, ...
        return None