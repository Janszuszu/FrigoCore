"""FrigoCore — Password hashing and JWT access tokens."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.models.user import User

ALGORITHM = "HS256"

# bcrypt's own primitive, not passlib's CryptContext wrapper — passlib 1.7.4
# (the last release) probes bcrypt internals that no longer exist on bcrypt
# >=4.1 and raises before it ever hashes anything. Calling bcrypt directly
# sidesteps that broken compatibility shim entirely.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    truncated = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


REFRESH_TYPE = "refresh"


def password_stamp(user: User) -> str:
    """A short fingerprint of the password hash: a refresh token carries it,
    so changing the password signs every phone out."""
    return hashlib.sha256(user.hashed_password.encode("utf-8")).hexdigest()[:16]


def create_refresh_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user.id),
        "typ": REFRESH_TYPE,
        "pwd": password_stamp(user),
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    payload = _decode(token)
    # A refresh token is only good for getting a new pair, never as a bearer.
    if payload is None or payload.get("typ") == REFRESH_TYPE:
        return None
    return payload


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    payload = _decode(token)
    if payload is None or payload.get("typ") != REFRESH_TYPE:
        return None
    return payload


def _decode(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        payload["sub"] = uuid.UUID(sub)
    except ValueError:
        return None
    return payload
