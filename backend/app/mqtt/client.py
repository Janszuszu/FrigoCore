"""FrigoCore — MQTT Engine.

Handles:
  - Connection to EMQX broker.
  - Topic subscription (wildcard #).
  - Topic parsing: {object.slug}/{sensor.slug}.
  - Payload validation (JSON with temperature field).
  - Writing Measurement to the database.
  - Updating Sensor.current_temperature and Sensor.last_message_at.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models.measurement import Measurement
from app.models.sensor import Sensor

from app.api.websocket import manager as ws_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QOS = 1
TOPIC_WILDCARD = "#"

# ---------------------------------------------------------------------------
# MQTT Engine
# ---------------------------------------------------------------------------


class MQTTEngine:
    """Async-compatible MQTT engine using paho-mqtt.

    The engine runs paho's network loop in a background thread (loop_start)
    and dispatches incoming messages to async database handlers via
    asyncio.run_coroutine_threadsafe().
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory

        self._client = mqtt.Client(
            client_id="frigocore-backend",
            protocol=mqtt.MQTTv5,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to the broker and begin processing messages."""
        self._loop = asyncio.get_running_loop()

        try:
            self._client.connect(
                self.settings.EMQX_HOST,
                self.settings.EMQX_PORT,
                keepalive=60,
            )
        except Exception as exc:
            logger.error("Failed to connect to MQTT broker: %s", exc)
            raise

        self._client.loop_start()
        logger.info(
            "MQTT engine started — broker %s:%d",
            self.settings.EMQX_HOST,
            self.settings.EMQX_PORT,
        )

    async def stop(self) -> None:
        """Gracefully disconnect."""
        self._client.unsubscribe(TOPIC_WILDCARD)
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("MQTT engine stopped")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: dict,
        reason_code: mqtt.ReasonCodes,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
            client.subscribe(TOPIC_WILDCARD, QOS)
            logger.info("Subscribed to topic: %s", TOPIC_WILDCARD)
        else:
            logger.error("MQTT connection failed — reason_code=%s", reason_code)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: dict,
        reason_code: mqtt.ReasonCodes,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code != 0:
            logger.warning("Unexpected MQTT disconnect — reason_code=%s", reason_code)
        else:
            logger.info("MQTT disconnected cleanly")

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: object,
        msg: mqtt.MQTTMessage,
    ) -> None:
        """Dispatch incoming message to async handler."""
        if self._loop is None:
            logger.error("MQTT engine not started — loop is None")
            return

        # Schedule the async handler in the main event loop
        asyncio.run_coroutine_threadsafe(
            self._handle_message(msg.topic, msg.payload),
            self._loop,
        )

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def _handle_message(self, topic: str, payload: bytes) -> None:
        """Parse topic, validate payload, persist measurement."""
        try:
            # 1. Parse topic → {object_slug}/{sensor_slug}
            object_slug, sensor_slug = self._parse_topic(topic)

            # 2. Parse and validate payload
            temperature = self._parse_payload(payload)

            # 3. Resolve sensor via slugs
            async with self.session_factory() as session:
                await self._persist_measurement(
                    session, object_slug, sensor_slug, temperature
                )
                await session.commit()

        except Exception:
            logger.exception("Failed to process MQTT message topic=%s", topic)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_topic(topic: str) -> tuple[str, str]:
        """Extract (object_slug, sensor_slug) from a topic string.

        Expected format: "object-slug/sensor-slug"
        """
        parts = topic.strip("/").split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid topic format, expected 'object/sensor': {topic!r}")
        return parts[0], parts[1]

    @staticmethod
    def _parse_payload(payload: bytes) -> float:
        """Parse and validate the MQTT payload.

        Expected JSON format: {"temperature": 4.2}
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON payload: {payload!r}") from exc

        temperature = data.get("temperature")
        if temperature is None:
            raise ValueError(f"Missing 'temperature' field in payload: {data}")

        try:
            return float(temperature)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid temperature value: {temperature!r}") from exc

    @staticmethod
    async def _persist_measurement(
        session: AsyncSession,
        object_slug: str,
        sensor_slug: str,
        temperature: float,
    ) -> None:
        """Look up the sensor by its slug and the object slug, then persist the measurement."""
        # Import Object here to avoid circular imports at module level
        from app.models.object import Object  # noqa: PLC0415

        # Resolve object + sensor
        stmt = (
            select(Sensor)
            .join(Sensor.object)
            .where(Object.slug == object_slug, Sensor.slug == sensor_slug)
        )
        result = await session.execute(stmt)
        sensor = result.scalar_one_or_none()

        if sensor is None:
            logger.warning(
                "Unknown topic — object_slug=%s sensor_slug=%s — ignoring message",
                object_slug,
                sensor_slug,
            )
            return

        now = datetime.now(timezone.utc)

        # Create measurement
        measurement = Measurement(
            sensor_id=sensor.id,
            temperature=temperature,
            received_at=now,
        )
        session.add(measurement)

        # Update sensor live telemetry
        sensor.current_temperature = temperature
        sensor.last_message_at = now
        session.add(sensor)

        logger.debug(
            "Measurement saved — sensor=%s/%s temp=%.2f",
            object_slug,
            sensor_slug,
            temperature,
        )

        # Broadcast WebSocket events
        await ws_manager.broadcast(
            "measurement.created",
            {
                "id": str(measurement.id),
                "sensor_id": str(sensor.id),
                "temperature": temperature,
                "received_at": now.isoformat(),
            },
        )
        await ws_manager.broadcast(
            "sensor.updated",
            {
                "id": str(sensor.id),
                "slug": sensor.slug,
                "current_temperature": temperature,
                "last_message_at": now.isoformat(),
            },
        )
