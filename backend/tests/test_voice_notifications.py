"""VoIPstudio voice-call notification channel + its admin settings API.

VoIPstudio itself is never contacted — every HTTP request is answered by an
httpx.MockTransport (or place_tts_call is replaced), so the tests assert on
exactly what would be sent.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from app.config import settings
from app.enums import AlarmType, NotificationChannel, UserRole
from app.models.alarm import Alarm
from app.models.app_setting import AppSetting
from app.models.notification_endpoint import NotificationEndpoint
from app.models.notification_profile import NotificationProfile
from app.services import notification_engine, voip_settings, voipstudio_client
from app.services.notification_engine import NotificationEngine, build_voice_message
from app.services.voip_settings import VoipConfig
from app.services.voipstudio_client import (
    VoipStudioCallError,
    VoipStudioNotConfiguredError,
    normalize_e164,
    ping,
    place_tts_call,
)
from tests.conftest import auth_headers
from tests.helpers import make_object

CONFIG = VoipConfig(api_token="test-token")
SETTINGS_URL = "/api/v1/settings/voip"
NUMBERS_URL = "/api/v1/settings/voip/numbers"


@pytest.fixture(autouse=True)
def _voip_api_url(monkeypatch):
    monkeypatch.setattr(settings, "VOIPSTUDIO_API_URL", "https://voip.test/v1.2/voipstudio")


def _recording_transport(status_code: int = 201, body: dict | None = None):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json=body if body is not None else {"data": {"id": 4655}})

    return httpx.MockTransport(handler), requests


def _make_alarm(alarm_type=AlarmType.HIGH_TEMPERATURE, value: float | None = 8.46) -> Alarm:
    return Alarm(
        id=uuid.uuid4(),
        alarm_type=alarm_type,
        object_id=uuid.uuid4(),
        trigger_value=value,
        detected_at=datetime.now(timezone.utc),
        description="High temperature alarm",
    )


def _voice_endpoint(phone_number="48600100200", is_enabled=True) -> NotificationEndpoint:
    return NotificationEndpoint(
        id=uuid.uuid4(),
        channel=NotificationChannel.VOICE,
        label="Serwis",
        config={"phone_number": phone_number},
        is_enabled=is_enabled,
    )


@pytest.fixture
def captured_calls(monkeypatch):
    """Replaces the real VoIPstudio call; records (number, message, config)."""
    calls: list[tuple[str, str, VoipConfig]] = []

    async def fake_place_tts_call(phone_number, message, config, **_kwargs):
        calls.append((phone_number, message, config))
        return 1

    monkeypatch.setattr(voipstudio_client, "place_tts_call", fake_place_tts_call)
    return calls


async def _save_token(db_session, token="saved-token", caller_id=""):
    await voip_settings.save(db_session, api_token=token, caller_id=caller_id)
    await db_session.commit()


# ---------------------------------------------------------------------------
# Phone number normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+48 600 100 200", "48600100200"),
        ("0048600100200", "48600100200"),
        ("600-100-200", "48600100200"),
        ("48600100200", "48600100200"),
        ("+44 20 3844 7110", "442038447110"),
    ],
)
def test_normalize_e164_accepts_common_formats(raw, expected):
    assert normalize_e164(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12345", "+48 600 100 200 300 400 5", "600 100 20x"])
def test_normalize_e164_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_e164(raw)


# ---------------------------------------------------------------------------
# VoIPstudio client
# ---------------------------------------------------------------------------


async def test_place_tts_call_sends_leadcall_with_auth_header():
    transport, requests = _recording_transport()
    config = VoipConfig(api_token="test-token", caller_id="+48 22 123 45 67")

    call_id = await place_tts_call("+48 600 100 200", "Uwaga, alarm", config, transport=transport)

    assert call_id == 4655
    [request] = requests
    assert request.method == "POST"
    assert str(request.url) == "https://voip.test/v1.2/voipstudio/leadcalls"
    assert request.headers["X-Auth-Token"] == "test-token"
    assert json.loads(request.content) == {
        "to": "48600100200",
        "tts": "Uwaga, alarm",
        "caller_id": "48221234567",
    }


async def test_place_tts_call_omits_caller_id_when_unset():
    transport, requests = _recording_transport()
    await place_tts_call("600100200", "x", CONFIG, transport=transport)
    assert "caller_id" not in json.loads(requests[0].content)


async def test_place_tts_call_without_token_raises():
    transport, requests = _recording_transport()
    with pytest.raises(VoipStudioNotConfiguredError):
        await place_tts_call("600100200", "x", VoipConfig(), transport=transport)
    assert requests == []


async def test_place_tts_call_raises_on_api_error():
    transport, _ = _recording_transport(400, {"message": "Validation error", "errors": ["to"]})
    with pytest.raises(VoipStudioCallError, match="HTTP 400") as excinfo:
        await place_tts_call("600100200", "x", CONFIG, transport=transport)
    assert excinfo.value.status_code == 400


async def test_ping_hits_ping_endpoint():
    transport, requests = _recording_transport(200, {"message": "Pong"})
    await ping(CONFIG, transport=transport)
    assert str(requests[0].url) == "https://voip.test/v1.2/voipstudio/ping"
    assert requests[0].headers["X-Auth-Token"] == "test-token"


# ---------------------------------------------------------------------------
# Voice message text
# ---------------------------------------------------------------------------


def test_voice_message_names_site_reason_and_value():
    message = build_voice_message(_make_alarm(), "Kotlety z Biskupca")
    assert "Obiekt: Kotlety z Biskupca." in message
    assert "Wysoka temperatura, aktualnie 8,5 stopni." in message
    # Repeated so a callee who picks up late still hears the site name.
    assert message.count("Kotlety z Biskupca") == 2


def test_voice_message_offline_has_no_temperature():
    message = build_voice_message(_make_alarm(AlarmType.OFFLINE, 900.0), "Chłodnia A")
    assert "Brak komunikacji z czujnikiem." in message
    assert "stopni" not in message


# ---------------------------------------------------------------------------
# NotificationEngine integration
# ---------------------------------------------------------------------------


async def test_alarm_calls_every_enabled_voice_endpoint_with_saved_config(db_session, captured_calls):
    await _save_token(db_session, caller_id="48221234567")
    endpoints = [
        _voice_endpoint("48600100200"),
        _voice_endpoint("48600999888"),
        _voice_endpoint("48500000000", is_enabled=False),
    ]

    await NotificationEngine.send_alarm_notification(_make_alarm(), endpoints, object_name="Chłodnia A")

    assert [number for number, _, _ in captured_calls] == ["48600100200", "48600999888"]
    assert all("Chłodnia A" in message for _, message, _ in captured_calls)
    config = captured_calls[0][2]
    assert (config.api_token, config.caller_id) == ("saved-token", "48221234567")


async def test_failed_call_does_not_block_remaining_endpoints(monkeypatch):
    dialled: list[str] = []

    async def flaky_place_tts_call(phone_number, message, config, **_kwargs):
        dialled.append(phone_number)
        if phone_number == "48600100200":
            raise VoipStudioCallError("VoIPstudio HTTP 500")
        return 1

    monkeypatch.setattr(voipstudio_client, "place_tts_call", flaky_place_tts_call)
    endpoints = [_voice_endpoint("48600100200"), _voice_endpoint("48600999888")]

    await NotificationEngine.send_alarm_notification(_make_alarm(), endpoints, object_name="A")

    assert dialled == ["48600100200", "48600999888"]


async def test_service_on_the_way_notice_never_rings_phones(captured_calls):
    await NotificationEngine.send_service_on_the_way(_make_alarm(), [_voice_endpoint()])
    assert captured_calls == []


async def test_unconfigured_voipstudio_is_logged_not_raised(monkeypatch):
    # caplog can't be used: Alembic's fileConfig disables app loggers.
    logger = MagicMock()
    monkeypatch.setattr(notification_engine, "logger", logger)

    await NotificationEngine.send_alarm_notification(_make_alarm(), [_voice_endpoint()], object_name="A")

    logger.error.assert_called_once()
    assert "VoIPstudio not configured" in logger.error.call_args.args[0]


# ---------------------------------------------------------------------------
# Generic notification-endpoint API — voice numbers validated + normalized
# ---------------------------------------------------------------------------


async def _object_with_profile(db_session):
    obj = await make_object(db_session)
    db_session.add(NotificationProfile(name="Profil", object_id=obj.id))
    await db_session.commit()
    return obj


async def test_api_creates_voice_endpoint_with_normalized_number(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await _object_with_profile(db_session)

    response = await client.post(
        f"/api/v1/objects/{obj.id}/notification-endpoints",
        json={"channel": "voice", "label": "Serwis", "config": {"phone_number": "+48 600 100 200"}},
        headers=auth_headers(admin),
    )

    assert response.status_code == 201, response.text
    assert response.json()["config"] == {"phone_number": "48600100200"}


async def test_api_rejects_invalid_voice_number_on_create_and_update(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await _object_with_profile(db_session)
    url = f"/api/v1/objects/{obj.id}/notification-endpoints"

    bad = await client.post(
        url, json={"channel": "voice", "config": {"phone_number": "123"}}, headers=auth_headers(admin)
    )
    assert bad.status_code == 422

    created = await client.post(
        url, json={"channel": "voice", "config": {"phone_number": "600100200"}}, headers=auth_headers(admin)
    )
    bad_update = await client.patch(
        f"{url}/{created.json()['id']}",
        json={"config": {"phone_number": "nope"}},
        headers=auth_headers(admin),
    )
    assert bad_update.status_code == 422


# ---------------------------------------------------------------------------
# Settings API — integration config
# ---------------------------------------------------------------------------


async def test_settings_token_is_encrypted_and_never_returned(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)

    empty = await client.get(SETTINGS_URL, headers=auth_headers(admin))
    assert empty.json()["token_configured"] is False

    saved = await client.patch(
        SETTINGS_URL,
        json={"api_token": "  abcdef1234567890  ", "caller_id": "+48 22 123 45 67"},
        headers=auth_headers(admin),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["token_configured"] is True
    assert body["token_hint"] == "7890"
    assert body["caller_id"] == "48221234567"
    assert "abcdef1234567890" not in saved.text

    row = await db_session.get(AppSetting, voip_settings.TOKEN_KEY)
    assert row.value and "abcdef1234567890" not in row.value
    assert (await voip_settings.load(db_session)).api_token == "abcdef1234567890"


async def test_settings_update_without_token_keeps_it_and_empty_clears_it(client, make_user):
    admin = await make_user(UserRole.ADMIN)
    await client.patch(SETTINGS_URL, json={"api_token": "tok-1234"}, headers=auth_headers(admin))

    kept = await client.patch(SETTINGS_URL, json={"caller_id": ""}, headers=auth_headers(admin))
    assert kept.json()["token_hint"] == "1234"

    cleared = await client.patch(SETTINGS_URL, json={"api_token": ""}, headers=auth_headers(admin))
    assert cleared.json()["token_configured"] is False


async def test_settings_reject_invalid_caller_id(client, make_user):
    admin = await make_user(UserRole.ADMIN)
    response = await client.patch(SETTINGS_URL, json={"caller_id": "abc"}, headers=auth_headers(admin))
    assert response.status_code == 422


async def test_settings_require_admin(client, make_user):
    user = await make_user(UserRole.SERWISANT)
    for method, url in [
        ("get", SETTINGS_URL),
        ("patch", SETTINGS_URL),
        ("post", f"{SETTINGS_URL}/test"),
        ("get", NUMBERS_URL),
    ]:
        kwargs = {"json": {}} if method in ("patch", "post") else {}
        response = await getattr(client, method)(url, headers=auth_headers(user), **kwargs)
        assert response.status_code == 403, (method, url, response.status_code)


async def test_connection_test_reports_missing_token(client, make_user):
    admin = await make_user(UserRole.ADMIN)
    response = await client.post(f"{SETTINGS_URL}/test", headers=auth_headers(admin))
    assert response.json() == {"ok": False, "detail": "Brak klucza API"}


async def test_connection_test_reports_rejected_token(client, db_session, make_user, monkeypatch):
    admin = await make_user(UserRole.ADMIN)
    await _save_token(db_session)

    async def rejecting_ping(config, **_kwargs):
        raise VoipStudioCallError("VoIPstudio HTTP 401: Authentication Failed", status_code=401)

    monkeypatch.setattr(voipstudio_client, "ping", rejecting_ping)
    response = await client.post(f"{SETTINGS_URL}/test", headers=auth_headers(admin))
    assert response.json() == {
        "ok": False,
        "detail": "VoIPstudio odrzuciło klucz API — jest nieprawidłowy lub wygasł",
    }


async def test_test_call_uses_saved_config(client, db_session, make_user, captured_calls):
    admin = await make_user(UserRole.ADMIN)
    await _save_token(db_session)

    response = await client.post(
        f"{SETTINGS_URL}/test-call", json={"phone_number": "600 100 200"}, headers=auth_headers(admin)
    )

    assert response.json()["ok"] is True
    number, _, config = captured_calls[0]
    assert (number, config.api_token) == ("48600100200", "saved-token")


# ---------------------------------------------------------------------------
# Settings API — per-object numbers
# ---------------------------------------------------------------------------


async def test_numbers_crud_creates_profile_on_demand(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await make_object(db_session, "Chłodnia B")  # no notification profile yet

    created = await client.post(
        NUMBERS_URL,
        json={"object_id": str(obj.id), "phone_number": "+48 600 100 200", "label": "Serwis"},
        headers=auth_headers(admin),
    )
    assert created.status_code == 201, created.text
    number = created.json()
    assert number["phone_number"] == "48600100200"

    listing = (await client.get(NUMBERS_URL, headers=auth_headers(admin))).json()
    assert listing == [{"object_id": str(obj.id), "object_name": "Chłodnia B", "numbers": [number]}]

    updated = await client.patch(
        f"{NUMBERS_URL}/{number['id']}", json={"is_enabled": False, "label": "Klient"}, headers=auth_headers(admin)
    )
    assert updated.json()["is_enabled"] is False
    assert updated.json()["label"] == "Klient"

    bad = await client.patch(f"{NUMBERS_URL}/{number['id']}", json={"phone_number": "12"}, headers=auth_headers(admin))
    assert bad.status_code == 422

    deleted = await client.delete(f"{NUMBERS_URL}/{number['id']}", headers=auth_headers(admin))
    assert deleted.status_code == 204
    listing = (await client.get(NUMBERS_URL, headers=auth_headers(admin))).json()
    assert listing[0]["numbers"] == []


async def test_numbers_for_unknown_object_is_404(client, make_user):
    admin = await make_user(UserRole.ADMIN)
    response = await client.post(
        NUMBERS_URL,
        json={"object_id": str(uuid.uuid4()), "phone_number": "600100200"},
        headers=auth_headers(admin),
    )
    assert response.status_code == 404


async def test_numbers_api_ignores_non_voice_endpoints(client, db_session, make_user):
    admin = await make_user(UserRole.ADMIN)
    obj = await _object_with_profile(db_session)
    email = await client.post(
        f"/api/v1/objects/{obj.id}/notification-endpoints",
        json={"channel": "email", "config": {"to": "a@b.pl"}},
        headers=auth_headers(admin),
    )

    listing = (await client.get(NUMBERS_URL, headers=auth_headers(admin))).json()
    assert listing[0]["numbers"] == []
    response = await client.delete(f"{NUMBERS_URL}/{email.json()['id']}", headers=auth_headers(admin))
    assert response.status_code == 404
