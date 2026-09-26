"""FrigoCore — symmetric encryption for third-party secrets stored in the DB.

Secrets an admin enters through the UI (e.g. the VoIPstudio API key) are
encrypted at rest with a Fernet key derived from SECRET_KEY, so a database
dump or backup alone does not leak them. Rotating SECRET_KEY makes existing
ciphertexts unreadable — the admin simply re-enters the secret.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SecretDecryptionError(RuntimeError):
    """Ciphertext cannot be decrypted with the current SECRET_KEY."""


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"frigocore-secret-box:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise SecretDecryptionError("Stored secret cannot be decrypted — was SECRET_KEY rotated?") from None
