"""FrigoCore — VoIPstudio configuration (admin-entered, stored in app_settings).

The API key is encrypted at rest and never returned to a client in full.
A background keepalive pings VoIPstudio daily: VoIPstudio keys expire after
N days *without use*, and alarms can be weeks apart — without the ping the
key would silently expire and the next alarm call would fail.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import secret_box
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

TOKEN_KEY = "voipstudio.api_token"
CALLER_ID_KEY = "voipstudio.caller_id"

KEEPALIVE_INTERVAL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class VoipConfig:
    api_token: str = ""
    caller_id: str = ""
    token_updated_at: datetime | None = None
    # True when a token is stored but cannot be decrypted (SECRET_KEY rotated).
    token_unreadable: bool = False

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token)


async def load(session: AsyncSession) -> VoipConfig:
    rows = {
        row.key: row
        for row in await session.scalars(
            select(AppSetting).where(AppSetting.key.in_([TOKEN_KEY, CALLER_ID_KEY]))
        )
    }
    token_row = rows.get(TOKEN_KEY)
    api_token, unreadable = "", False
    if token_row is not None and token_row.value:
        try:
            api_token = secret_box.decrypt(token_row.value)
        except secret_box.SecretDecryptionError:
            logger.error("Stored VoIPstudio API key cannot be decrypted — re-enter it in Ustawienia")
            unreadable = True
    caller_row = rows.get(CALLER_ID_KEY)
    return VoipConfig(
        api_token=api_token,
        caller_id=caller_row.value if caller_row is not None else "",
        token_updated_at=token_row.updated_at if token_row is not None and token_row.value else None,
        token_unreadable=unreadable,
    )


async def save(
    session: AsyncSession,
    *,
    api_token: str | None = None,
    caller_id: str | None = None,
) -> None:
    """Persist the given fields; None leaves a field unchanged, "" clears it."""
    if api_token is not None:
        await _upsert(session, TOKEN_KEY, secret_box.encrypt(api_token) if api_token else "")
    if caller_id is not None:
        await _upsert(session, CALLER_ID_KEY, caller_id)


async def _upsert(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value


class VoipKeepalive:
    """Pings VoIPstudio once a day so an unused API key never expires."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        from app.services import voipstudio_client  # noqa: PLC0415 — avoid import cycle

        while True:
            try:
                async with self._session_factory() as session:
                    config = await load(session)
                if config.is_configured:
                    await voipstudio_client.ping(config)
                    logger.info("[Voice] VoIPstudio keepalive ping OK")
            except Exception:
                # Keep looping: a transient outage must not kill the keepalive.
                logger.exception("[Voice] VoIPstudio keepalive ping failed")
            await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
