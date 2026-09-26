"""FrigoCore — VoIPstudio REST API client (outbound alarm voice calls).

Places a call to an E.164 number and reads a text-to-speech message to the
callee via `POST /leadcalls`. Authentication is a permanent API key
(user_token) generated in the VoIPstudio dashboard (Administration -> Users
-> API Keys) and sent in the `X-Auth-Token` header.

Docs: https://voipstudio.com/docs/api/introduction/
      https://voipstudio.com/docs/api/resources/calls/
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# A phone call is not worth holding the alarm pipeline hostage for — a hung
# VoIPstudio API must fail fast so the remaining endpoints still get notified.
_REQUEST_TIMEOUT_SECONDS = 10.0

# Polish national numbers are 9 digits; anything that short with no country
# code is assumed to be a PL number, since every FrigoCore site is in Poland.
_DEFAULT_COUNTRY_CODE = "48"
_NATIONAL_NUMBER_LENGTH = 9


class VoipStudioNotConfiguredError(RuntimeError):
    """VOIPSTUDIO_API_TOKEN is not set — calls cannot be placed."""


class VoipStudioCallError(RuntimeError):
    """VoIPstudio rejected the call request (non-2xx response)."""


def normalize_e164(phone_number: str) -> str:
    """Return the digits-only E.164 form VoIPstudio expects (no leading '+').

    Accepts common human input: '+48 600 100 200', '0048600100200',
    '600-100-200'. Raises ValueError for anything that cannot be a valid
    E.164 number, so a typo is rejected instead of dialling a wrong number.
    """
    digits = re.sub(r"[\s\-().]", "", phone_number or "")
    if digits.startswith("+"):
        digits = digits[1:]
    elif digits.startswith("00"):
        digits = digits[2:]
    elif len(digits) == _NATIONAL_NUMBER_LENGTH:
        digits = _DEFAULT_COUNTRY_CODE + digits

    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise ValueError(f"Invalid phone number: {phone_number!r}")
    return digits


async def place_tts_call(
    phone_number: str,
    message: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int | None:
    """Call `phone_number` and read `message` to the callee.

    Returns the VoIPstudio call id. `transport` exists for tests only.
    """
    token = settings.VOIPSTUDIO_API_TOKEN
    if not token:
        raise VoipStudioNotConfiguredError("VOIPSTUDIO_API_TOKEN is not set")

    body: dict[str, str] = {"to": normalize_e164(phone_number), "tts": message}
    if settings.VOIPSTUDIO_CALLER_ID:
        body["caller_id"] = normalize_e164(settings.VOIPSTUDIO_CALLER_ID)

    async with httpx.AsyncClient(
        base_url=settings.VOIPSTUDIO_API_URL.rstrip("/") + "/",
        headers={"X-Auth-Token": token},
        timeout=_REQUEST_TIMEOUT_SECONDS,
        transport=transport,
    ) as client:
        response = await client.post("leadcalls", json=body)

    if response.is_error:
        # The body carries VoIPstudio's validation message; the token is
        # only ever in the request headers, so it is safe to log.
        raise VoipStudioCallError(f"VoIPstudio HTTP {response.status_code}: {response.text[:500]}")

    call_id = (response.json().get("data") or {}).get("id")
    logger.info("[Voice] call placed to=%s voipstudio_call_id=%s", body["to"], call_id)
    return call_id
