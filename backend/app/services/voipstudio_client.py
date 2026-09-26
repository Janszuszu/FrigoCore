"""FrigoCore — VoIPstudio REST API client (outbound alarm voice calls).

Places a call to an E.164 number and reads a text-to-speech message to the
callee via `POST /leadcalls`. Authentication is an API key (user_token)
generated in the VoIPstudio dashboard (Administration -> Users -> API Keys),
entered by an admin in Ustawienia and sent in the `X-Auth-Token` header.

Docs: https://voipstudio.com/docs/api/introduction/
      https://voipstudio.com/docs/api/resources/calls/
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings
from app.services.voip_settings import VoipConfig

logger = logging.getLogger(__name__)

# Plain API requests answer in well under a second.
_REQUEST_TIMEOUT_SECONDS = 10.0
# POST /leadcalls can hold the response open while the call is being set up.
# Alarm calls run as background tasks (see notification_engine), so a long
# wait here never blocks the alarm pipeline.
_CALL_TIMEOUT_SECONDS = 60.0

# Polish national numbers are 9 digits; anything that short with no country
# code is assumed to be a PL number, since every FrigoCore site is in Poland.
_DEFAULT_COUNTRY_CODE = "48"
_NATIONAL_NUMBER_LENGTH = 9


class VoipStudioNotConfiguredError(RuntimeError):
    """No VoIPstudio API key is configured — calls cannot be placed."""


class VoipStudioNoCallerIdError(VoipStudioNotConfiguredError):
    """No caller ID set — /leadcalls requires one of the account's numbers."""


class VoipStudioCallError(RuntimeError):
    """VoIPstudio rejected the request (non-2xx response)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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


def _client(
    config: VoipConfig,
    transport: httpx.AsyncBaseTransport | None,
    timeout: float = _REQUEST_TIMEOUT_SECONDS,
) -> httpx.AsyncClient:
    if not config.is_configured:
        raise VoipStudioNotConfiguredError("VoIPstudio API key is not configured")
    return httpx.AsyncClient(
        base_url=settings.VOIPSTUDIO_API_URL.rstrip("/") + "/",
        headers={"X-Auth-Token": config.api_token},
        timeout=timeout,
        transport=transport,
    )


def _raise_for_error(response: httpx.Response) -> None:
    if response.is_error:
        # The body carries VoIPstudio's validation message; the key is only
        # ever in the request headers, so the body is safe to log/return.
        raise VoipStudioCallError(
            f"VoIPstudio HTTP {response.status_code}: {response.text[:500]}",
            status_code=response.status_code,
        )


async def place_tts_call(
    phone_number: str,
    message: str,
    config: VoipConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int | None:
    """Call `phone_number` and read `message` to the callee.

    Returns the VoIPstudio call id. `transport` exists for tests only.
    """
    if not config.caller_id:
        # /leadcalls rejects a missing caller ID and "anonymous" alike
        # ("DDI not found"): it must be an active number on the account.
        raise VoipStudioNoCallerIdError("VoIPstudio caller ID (account number) is not configured")
    body: dict[str, str] = {
        "to": normalize_e164(phone_number),
        "tts": message,
        "caller_id": normalize_e164(config.caller_id),
    }

    logger.info("[Voice] placing call to=%s", body["to"])
    async with _client(config, transport, _CALL_TIMEOUT_SECONDS) as client:
        response = await client.post("leadcalls", json=body)
    _raise_for_error(response)

    call_id = (response.json().get("data") or {}).get("id")
    logger.info("[Voice] call placed to=%s voipstudio_call_id=%s", body["to"], call_id)
    return call_id


async def ping(config: VoipConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
    """Verify the API key and reset its inactivity-expiry timer."""
    async with _client(config, transport) as client:
        response = await client.get("ping")
    _raise_for_error(response)
