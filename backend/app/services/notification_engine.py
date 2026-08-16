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
from typing import TYPE_CHECKING, Any

from app.enums import NotificationChannel
from app.models.alarm import Alarm
from app.models.notification_endpoint import NotificationEndpoint
from app.services import firebase_client
from app.services.firebase_client import FcmSendResult, FirebaseNotConfiguredError

if TYPE_CHECKING:
    from app.models.alarm_assignment import AlarmAssignment
    from app.models.device_token import DeviceToken
    from app.models.object import Object

logger = logging.getLogger(__name__)

# Payload contract version for the future Android client. Bump only on a
# breaking shape change — additive fields don't require a bump.
SERVICE_ALARM_PAYLOAD_VERSION = 1


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
    # Service dispatch (technician-facing FCM push)
    # ------------------------------------------------------------------

    @staticmethod
    async def send_service_alarm_dispatch(
        alarm: Alarm,
        obj: "Object",
        assignment: "AlarmAssignment",
        device_tokens: list["DeviceToken"],
    ) -> None:
        """Push the versioned SERVICE_ALARM payload to every active device
        token of the assignment's target(s).

        This is deliberately separate from `send_alarm_notification` — that
        method fans out to an Object's NotificationProfile (client-facing
        channels); this one fans out to a technician's own registered
        devices and always uses FCM.
        """
        active_tokens = [device for device in device_tokens if device.is_active]
        if not active_tokens:
            logger.info(
                "No active device tokens for assignment %s — skipping dispatch push",
                assignment.id,
            )
            return

        payload = build_service_alarm_payload(alarm, obj, assignment)

        # Resolve the Firebase app once up front: if credentials are missing
        # or invalid, this is a hard failure for the whole batch — raise
        # rather than silently skipping devices one by one, so the caller's
        # audit trail does not end up claiming a notification was sent.
        firebase_client.get_firebase_app()

        for device in active_tokens:
            result = firebase_client.send_to_token(device.fcm_token, payload)
            if result == FcmSendResult.SENT:
                logger.info(
                    "[FCM] service_alarm sent user=%s assignment=%s",
                    device.user_id,
                    assignment.id,
                )
            elif result == FcmSendResult.INVALID_TOKEN:
                device.is_active = False
                logger.info(
                    "Deactivated invalid FCM token for user=%s assignment=%s",
                    device.user_id,
                    assignment.id,
                )
            else:
                logger.warning(
                    "FCM send error for user=%s assignment=%s — device left active",
                    device.user_id,
                    assignment.id,
                )

    # ------------------------------------------------------------------
    # Client-facing "service is on the way" (EN_ROUTE gating)
    # ------------------------------------------------------------------

    @staticmethod
    async def send_service_on_the_way(
        alarm: Alarm,
        endpoints: list[NotificationEndpoint],
    ) -> None:
        """Notify the client that a technician is travelling to the site.

        Must be called ONLY on the EN_ROUTE transition — never on TRIGGERED
        or ACKNOWLEDGED, which would needlessly alarm the client before
        service is actually confirmed under way.
        """
        if not endpoints:
            logger.info("No notification endpoints configured — skipping en-route notice for alarm %s", alarm.id)
            return

        payload = _build_alarm_payload(alarm)
        payload["subject"] = "FrigoCore — Serwis w drodze"
        payload["message"] = "Serwis został wysłany i jest w drodze na obiekt."

        for endpoint in endpoints:
            if not endpoint.is_enabled:
                continue
            try:
                await NotificationEngine._dispatch(endpoint, payload)
            except Exception:
                logger.exception(
                    "Failed to send en-route notice — endpoint=%s channel=%s",
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
        token = endpoint.config.get("device_token")
        if not token:
            logger.warning("FCM endpoint %s has no device_token configured", endpoint.id)
            return
        try:
            result = firebase_client.send_to_token(token, payload)
        except FirebaseNotConfiguredError:
            logger.error("Firebase not configured — cannot send FCM to endpoint %s", endpoint.id)
            return
        if result == FcmSendResult.INVALID_TOKEN:
            logger.warning("FCM token invalid for endpoint %s", endpoint.id)

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


def build_service_alarm_payload(
    alarm: Alarm,
    obj: "Object",
    assignment: "AlarmAssignment",
) -> dict[str, Any]:
    """Build the versioned SERVICE_ALARM push payload for the Android client.

    Stable, deterministic shape — additive-only changes without bumping
    SERVICE_ALARM_PAYLOAD_VERSION; a client on an older version must still be
    able to parse a payload built by a newer backend.
    """
    alarm_type = _enum_value(alarm.alarm_type)
    return {
        "type": "SERVICE_ALARM",
        "version": SERVICE_ALARM_PAYLOAD_VERSION,
        "alarm_id": str(alarm.id),
        "assignment_id": str(assignment.id),
        "tier": assignment.tier,
        "site_id": str(obj.id),
        "site_name": obj.name,
        "alarm_type": alarm_type.upper(),
        "severity": "CRITICAL",
        "title": "ALARM KRYTYCZNY",
        "message": alarm.description,
        "sensor_name": alarm.sensor_name,
        "requires_action": True,
        "created_at": alarm.detected_at.isoformat(),
        "dispatched_at": assignment.dispatched_at.isoformat(),
    }


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