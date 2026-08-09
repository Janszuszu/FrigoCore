"""FrigoCore — Notification Engine.

Handles dispatching alarm notifications to configured endpoints
for the object associated with the alarm.

Supported channels:
  - Telegram
  - FCM (Firebase Cloud Messaging)
  - Email
  - SMS
  - Webhook

Each channel handler is a separate method. In production, these would
integrate with external SDKs (python-telegram-bot, firebase-admin,
smtplib, twilio, httpx). Here, we log the notification payload.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.enums import NotificationChannel
from app.models.alarm import Alarm
from app.models.notification_endpoint import NotificationEndpoint

logger = logging.getLogger(__name__)


class NotificationEngine:
    """Stateless dispatcher for alarm notifications."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    async def send_alarm_notification(
        alarm: Alarm,
        endpoints: list[NotificationEndpoint],
    ) -> None:
        """Send an alarm notification to all provided endpoints.

        Args:
            alarm: The triggered alarm instance.
            endpoints: List of notification endpoints configured for the object.
        """
        if not endpoints:
            logger.info("No notification endpoints configured — skipping alarm %s", alarm.id)
            return

        payload = _build_alarm_payload(alarm)

        for endpoint in endpoints:
            if not endpoint.is_enabled:
                continue

            try:
                await NotificationEngine._dispatch(endpoint, payload)
            except Exception:
                logger.exception(
                    "Failed to send notification — endpoint=%s channel=%s",
                    endpoint.id,
                    endpoint.channel,
                )

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    @staticmethod
    async def _dispatch(endpoint: NotificationEndpoint, payload: dict[str, Any]) -> None:
        """Route the notification to the appropriate channel handler."""
        channel_handlers = {
            NotificationChannel.TELEGRAM: NotificationEngine._send_telegram,
            NotificationChannel.FCM: NotificationEngine._send_fcm,
            NotificationChannel.EMAIL: NotificationEngine._send_email,
            NotificationChannel.SMS: NotificationEngine._send_sms,
            NotificationChannel.WEBHOOK: NotificationEngine._send_webhook,
        }

        handler = channel_handlers.get(endpoint.channel)
        if handler is None:
            logger.warning("Unknown notification channel: %s", endpoint.channel)
            return

        await handler(endpoint, payload)

    # ------------------------------------------------------------------
    # Channel handlers (stubs — log the payload)
    # ------------------------------------------------------------------

    @staticmethod
    async def _send_telegram(endpoint: NotificationEndpoint, payload: dict[str, Any]) -> None:
        """Send alarm via Telegram bot."""
        logger.info(
            "[Telegram] to=%s payload=%s",
            endpoint.config.get("chat_id", "unknown"),
            json.dumps(payload, default=str),
        )
        # TODO: Integrate with python-telegram-bot

    @staticmethod
    async def _send_fcm(endpoint: NotificationEndpoint, payload: dict[str, Any]) -> None:
        """Send push notification via Firebase Cloud Messaging."""
        logger.info(
            "[FCM] device=%s payload=%s",
            endpoint.config.get("device_token", "unknown"),
            json.dumps(payload, default=str),
        )
        # TODO: Integrate with firebase-admin

    @staticmethod
    async def _send_email(endpoint: NotificationEndpoint, payload: dict[str, Any]) -> None:
        """Send alarm via Email (SMTP)."""
        logger.info(
            "[Email] to=%s subject=%s",
            endpoint.config.get("to", "unknown"),
            payload.get("subject", "Alarm"),
        )
        # TODO: Integrate with smtplib / aiosmtplib

    @staticmethod
    async def _send_sms(endpoint: NotificationEndpoint, payload: dict[str, Any]) -> None:
        """Send alarm via SMS."""
        logger.info(
            "[SMS] to=%s message=%s",
            endpoint.config.get("phone_number", "unknown"),
            payload.get("message", "Alarm"),
        )
        # TODO: Integrate with Twilio / SMS provider

    @staticmethod
    async def _send_webhook(endpoint: NotificationEndpoint, payload: dict[str, Any]) -> None:
        """Send alarm via Webhook (HTTP POST)."""
        logger.info(
            "[Webhook] url=%s payload=%s",
            endpoint.config.get("url", "unknown"),
            json.dumps(payload, default=str),
        )
        # TODO: Integrate with httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enum_value(value: Any) -> str:
    """Return the plain string for a value that may be an enum or a str.

    alarm_type and status are String columns, so SQLAlchemy hands them back
    as plain `str` when an Alarm is loaded from the database, and as an
    AlarmType/AlarmStatus only while the instance is still the one that was
    just constructed in memory. Assuming `.value` therefore raised
    AttributeError on every alarm read back from the database.
    """
    return value.value if hasattr(value, "value") else str(value)


def _build_alarm_payload(alarm: Alarm) -> dict[str, Any]:
    """Build a notification payload from an alarm."""
    alarm_type = _enum_value(alarm.alarm_type)
    return {
        "alarm_id": str(alarm.id),
        "alarm_type": alarm_type,
        "status": _enum_value(alarm.status),
        "trigger_value": alarm.trigger_value,
        "detected_at": alarm.detected_at.isoformat(),
        "triggered_at": alarm.triggered_at.isoformat() if alarm.triggered_at else None,
        "description": alarm.description,
        "object_id": str(alarm.object_id),
        "sensor_id": str(alarm.sensor_id) if alarm.sensor_id else None,
        "subject": f"FrigoCore Alarm — {alarm_type.upper()}",
        "message": alarm.description,
    }