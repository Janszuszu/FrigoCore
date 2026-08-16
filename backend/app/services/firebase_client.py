"""FrigoCore — Firebase Admin SDK initialization.

Owns the one-time Firebase Admin App instance and the low-level FCM send
call. Kept isolated from the alarm state machine and NotificationEngine so
that neither has to know how Firebase is configured or initialized — they
only see `get_firebase_app()` / `send_to_token()` / `FcmSendResult`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import firebase_admin
from firebase_admin import credentials, exceptions as firebase_exceptions, messaging

from app.config import settings

logger = logging.getLogger(__name__)

_app: Optional[firebase_admin.App] = None


class FirebaseNotConfiguredError(RuntimeError):
    """Firebase is needed but FIREBASE_CREDENTIALS_PATH is missing or invalid.

    Raised rather than silently returning None so a caller cannot mistake
    "not configured" for "there was nothing to send".
    """


def get_firebase_app() -> firebase_admin.App:
    """Return the singleton Firebase Admin App, initializing it exactly once.

    Safe to call from every notification path (background escalation engine,
    request handlers) without re-initializing on every call — and safe
    across multiple imports of this module, since it also recognizes an
    app initialized elsewhere in the process.
    """
    global _app
    if _app is not None:
        return _app

    if firebase_admin._apps:
        _app = firebase_admin.get_app()
        return _app

    if not settings.FIREBASE_CREDENTIALS_PATH:
        raise FirebaseNotConfiguredError(
            "FIREBASE_CREDENTIALS_PATH is not set — cannot send FCM notifications."
        )
    try:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        _app = firebase_admin.initialize_app(cred)
    except Exception as exc:
        raise FirebaseNotConfiguredError(
            f"Failed to initialize Firebase Admin SDK from FIREBASE_CREDENTIALS_PATH: {exc}"
        ) from exc
    return _app


class FcmSendResult:
    """Outcome of a single per-token FCM send — never an exception, so a
    caller fanning out to many devices can keep going after a bad one."""

    SENT = "sent"
    INVALID_TOKEN = "invalid_token"
    ERROR = "error"


def send_to_token(token: str, data: dict[str, Any]) -> str:
    """Send one FCM data message. Returns a FcmSendResult constant.

    FCM data payloads only accept string values, so every payload value is
    stringified here — the caller passes the payload shape unchanged.

    Raises FirebaseNotConfiguredError if Firebase itself cannot be reached
    at all (missing/invalid credentials) — that is a hard failure for the
    whole batch, unlike a single bad token.
    """
    app = get_firebase_app()
    message = messaging.Message(token=token, data={k: str(v) for k, v in data.items()})
    try:
        messaging.send(message, app=app)
        return FcmSendResult.SENT
    except messaging.UnregisteredError:
        logger.info("FCM token no longer registered — will be deactivated")
        return FcmSendResult.INVALID_TOKEN
    except firebase_exceptions.FirebaseError:
        logger.exception("FCM send failed")
        return FcmSendResult.ERROR
