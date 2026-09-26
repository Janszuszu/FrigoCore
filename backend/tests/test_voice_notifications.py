"""VoIPstudio voice-call notification channel.

VoIPstudio itself is never contacted — every HTTP request is answered by an
httpx.MockTransport, so the tests assert on exactly what would be sent.
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
from app.models.notification_endpoint import NotificationEndpoint
from app.models.notification_profile import NotificationProfile
from app.services import notification_engine, voipstudio_client
from app.services.notification_engine import NotificationEngine, build_voice_message
from app.services.voipstudio_client import (
    VoipStudioCallError,
    VoipStudioNotConfiguredError,
    normalize_e164,
    place_tts_call,
)
from tests.conftest import auth_headers
from tests.helpers import make_object


@pytest.fixture
def voip_configured(monkeypatch):
    monkeypatch.setattr(settings, "VOIPSTUDIO_API_TOKEN", "test-token")
    monkeypatch.setattr(settings, "VOIPSTUDIO_API_URL", "https://voip.test/v1.2/voipstudio")
    monkeypatch.setattr(settings, "VOIPSTUDIO_CALLER_ID", "")


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


async def test_place_tts_call_sends_leadcall_with_auth_header(voip_configured, monkeypatch):
    monkeypatch.setattr(settings, "VOIPSTUDIO_CALLER_ID", "+48 22 123 45 67")
    transport, requests = _recording_transport()

    call_id = await place_tts_call("+48 600 100 200", "Uwaga, alarm", transport=transport)

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


async def test_place_tts_call_omits_caller_id_when_unset(voip_configured):
    transport, requests = _recording_transport()
    await place_tts_call("600100200", "x", transport=transport)
    assert "caller_id" not in json.loads(requests[0].content)


async def test_place_tts_call_without_token_raises(monkeypatch):
    monkeypatch.setattr(settings, "VOIPSTUDIO_API_TOKEN", "")
    transport, requests = _recording_transport()
    with pytest.raises(VoipStudioNotConfiguredError):
        await place_tts_call("600100200", "x", transport=transport)
    assert requests == []


async def test_place_tts_call_raises_on_api_error(voip_configured):
    transport, _ = _recording_transport(400, {"message": "Validation error", "errors": ["to"]})
    with pytest.raises(VoipStudioCallError, match="HTTP 400"):
        await place_tts_call("600100200", "x", transport=transport)


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


@pytest.fixture
def captured_calls(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_place_tts_call(phone_number, message, **_kwargs):
        calls.append((phone_number, message))
        return 1

    monkeypatch.setattr(voipstudio_client, "place_tts_call", fake_place_tts_call)
    return calls


async def test_alarm_calls_every_enabled_voice_endpoint(captured_calls):
    endpoints = [
        _voice_endpoint("48600100200"),
        _voice_endpoint("48600999888"),
        _voice_endpoint("48500000000", is_enabled=False),
    ]
    await NotificationEngine.send_alarm_notification(_make_alarm(), endpoints, object_name="Chłodnia A")

    assert [number for number, _ in captured_calls] == ["48600100200", "48600999888"]
    assert all("Chłodnia A" in message for _, message in captured_calls)


async def test_failed_call_does_not_block_remaining_endpoints(monkeypatch):
    dialled: list[str] = []

    async def flaky_place_tts_call(phone_number, message, **_kwargs):
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
    monkeypatch.setattr(settings, "VOIPSTUDIO_API_TOKEN", "")

    await NotificationEngine.send_alarm_notification(_make_alarm(), [_voice_endpoint()], object_name="A")

    logger.error.assert_called_once()
    assert "VoIPstudio not configured" in logger.error.call_args.args[0]


# ---------------------------------------------------------------------------
# API — voice endpoints are validated and stored normalized
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
