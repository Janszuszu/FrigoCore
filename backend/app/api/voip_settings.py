"""FrigoCore — admin settings for alarm voice calls (VoIPstudio).

Two concerns, both admin-only:
  * the VoIPstudio integration itself — API key, caller ID, connection test;
  * which phone numbers get called for each object's alarms. Numbers are
    ordinary "voice" NotificationEndpoints in the object's
    NotificationProfile, so the alarm pipeline needs no special casing.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_admin
from app.database import get_db
from app.enums import NotificationChannel
from app.models.notification_endpoint import NotificationEndpoint
from app.models.notification_profile import NotificationProfile
from app.models.object import Object
from app.schemas import (
    ObjectVoiceNumbers,
    VoiceNumberCreate,
    VoiceNumberResponse,
    VoiceNumberUpdate,
    VoipSettingsResponse,
    VoipSettingsUpdate,
    VoipTestCallRequest,
    VoipTestResult,
)
from app.services import voip_settings, voipstudio_client
from app.services.voipstudio_client import normalize_e164

voip_router = APIRouter(dependencies=[Depends(require_admin)])

TEST_CALL_MESSAGE = (
    "To jest połączenie testowe systemu FrigoCore. "
    "Powiadomienia głosowe o alarmach działają poprawnie."
)


def _phone_or_422(raw: str) -> str:
    try:
        return normalize_e164(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="Nieprawidłowy numer telefonu") from None


def _failure(exc: Exception) -> VoipTestResult:
    if isinstance(exc, voipstudio_client.VoipStudioNotConfiguredError):
        return VoipTestResult(ok=False, detail="Brak klucza API")
    if isinstance(exc, voipstudio_client.VoipStudioCallError):
        if exc.status_code == 401:
            return VoipTestResult(ok=False, detail="VoIPstudio odrzuciło klucz API — jest nieprawidłowy lub wygasł")
        return VoipTestResult(ok=False, detail=str(exc))
    # Network errors / timeouts — the class name is enough, never a traceback.
    return VoipTestResult(ok=False, detail=f"Brak połączenia z VoIPstudio ({type(exc).__name__})")


# ---------------------------------------------------------------------------
# Integration config
# ---------------------------------------------------------------------------


def _settings_response(config: voip_settings.VoipConfig) -> VoipSettingsResponse:
    return VoipSettingsResponse(
        token_configured=config.is_configured,
        token_hint=config.api_token[-4:] if config.is_configured else None,
        token_updated_at=config.token_updated_at,
        token_unreadable=config.token_unreadable,
        caller_id=config.caller_id,
    )


@voip_router.get("", response_model=VoipSettingsResponse)
async def get_voip_settings(db: AsyncSession = Depends(get_db)) -> VoipSettingsResponse:
    return _settings_response(await voip_settings.load(db))


@voip_router.patch("", response_model=VoipSettingsResponse)
async def update_voip_settings(
    body: VoipSettingsUpdate, db: AsyncSession = Depends(get_db)
) -> VoipSettingsResponse:
    api_token = body.api_token.strip() if body.api_token is not None else None
    caller_id = body.caller_id.strip() if body.caller_id is not None else None
    if caller_id:
        caller_id = _phone_or_422(caller_id)
    await voip_settings.save(db, api_token=api_token, caller_id=caller_id)
    await db.commit()
    return _settings_response(await voip_settings.load(db))


@voip_router.post("/test", response_model=VoipTestResult)
async def test_voip_connection(db: AsyncSession = Depends(get_db)) -> VoipTestResult:
    config = await voip_settings.load(db)
    try:
        await voipstudio_client.ping(config)
    except Exception as exc:
        return _failure(exc)
    return VoipTestResult(ok=True, detail="Połączenie z VoIPstudio działa")


@voip_router.post("/test-call", response_model=VoipTestResult)
async def place_test_call(body: VoipTestCallRequest, db: AsyncSession = Depends(get_db)) -> VoipTestResult:
    phone_number = _phone_or_422(body.phone_number)
    config = await voip_settings.load(db)
    try:
        call_id = await voipstudio_client.place_tts_call(phone_number, TEST_CALL_MESSAGE, config)
    except Exception as exc:
        return _failure(exc)
    return VoipTestResult(ok=True, detail=f"Połączenie zlecone (id {call_id}) na numer +{phone_number}")


# ---------------------------------------------------------------------------
# Per-object phone numbers
# ---------------------------------------------------------------------------


def _number_response(endpoint: NotificationEndpoint, object_id: UUID) -> VoiceNumberResponse:
    return VoiceNumberResponse(
        id=endpoint.id,
        object_id=object_id,
        phone_number=str(endpoint.config.get("phone_number", "")),
        label=endpoint.label,
        is_enabled=endpoint.is_enabled,
    )


async def _voice_endpoint_or_404(db: AsyncSession, endpoint_id: UUID) -> tuple[NotificationEndpoint, UUID]:
    endpoint = await db.get(NotificationEndpoint, endpoint_id)
    if endpoint is None or endpoint.channel != NotificationChannel.VOICE:
        raise HTTPException(status_code=404, detail="Numer nie istnieje")
    profile = await db.get(NotificationProfile, endpoint.profile_id)
    return endpoint, profile.object_id


@voip_router.get("/numbers", response_model=list[ObjectVoiceNumbers])
async def list_voice_numbers(db: AsyncSession = Depends(get_db)) -> list[ObjectVoiceNumbers]:
    objects = await db.scalars(
        select(Object)
        .options(selectinload(Object.notification_profile).selectinload(NotificationProfile.endpoints))
        .order_by(Object.name)
    )
    result = []
    for obj in objects:
        endpoints = obj.notification_profile.endpoints if obj.notification_profile else []
        numbers = sorted(
            (e for e in endpoints if e.channel == NotificationChannel.VOICE),
            key=lambda e: e.created_at,
        )
        result.append(
            ObjectVoiceNumbers(
                object_id=obj.id,
                object_name=obj.name,
                numbers=[_number_response(e, obj.id) for e in numbers],
            )
        )
    return result


@voip_router.post("/numbers", response_model=VoiceNumberResponse, status_code=status.HTTP_201_CREATED)
async def add_voice_number(body: VoiceNumberCreate, db: AsyncSession = Depends(get_db)) -> VoiceNumberResponse:
    phone_number = _phone_or_422(body.phone_number)
    obj = await db.get(Object, body.object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Obiekt nie istnieje")
    profile = await db.scalar(
        select(NotificationProfile).where(NotificationProfile.object_id == obj.id)
    )
    if profile is None:
        # Objects created without notification settings have no profile yet.
        profile = NotificationProfile(name=obj.name, object_id=obj.id)
        db.add(profile)
        await db.flush()
    endpoint = NotificationEndpoint(
        profile_id=profile.id,
        channel=NotificationChannel.VOICE,
        label=body.label.strip(),
        config={"phone_number": phone_number},
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return _number_response(endpoint, obj.id)


@voip_router.patch("/numbers/{endpoint_id}", response_model=VoiceNumberResponse)
async def update_voice_number(
    endpoint_id: UUID, body: VoiceNumberUpdate, db: AsyncSession = Depends(get_db)
) -> VoiceNumberResponse:
    endpoint, object_id = await _voice_endpoint_or_404(db, endpoint_id)
    if body.phone_number is not None:
        endpoint.config = {**endpoint.config, "phone_number": _phone_or_422(body.phone_number)}
    if body.label is not None:
        endpoint.label = body.label.strip()
    if body.is_enabled is not None:
        endpoint.is_enabled = body.is_enabled
    await db.commit()
    await db.refresh(endpoint)
    return _number_response(endpoint, object_id)


@voip_router.delete("/numbers/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_voice_number(endpoint_id: UUID, db: AsyncSession = Depends(get_db)) -> Response:
    endpoint, _ = await _voice_endpoint_or_404(db, endpoint_id)
    await db.delete(endpoint)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
