"""FrigoCore — MQTT Engine.

Handles:
  - Connection to EMQX broker.
  - Topic subscription (wildcard #).
  - Mapping incoming MQTT topic directly to sensor.mqtt_topic.
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

        # Set authentication if credentials are provided
        if self.settings.MQTT_USER and self.settings.MQTT_PASSWORD:
            self._client.username_pw_set(
                self.settings.MQTT_USER,
                self.settings.MQTT_PASSWORD,
            )
            logger.info(
                "MQTT auth configured — user=%s",
                self.settings.MQTT_USER,
            )
        else:
            logger.warning("MQTT credentials not provided — connecting without authentication")
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
        """Map MQTT topic to sensor, validate payload, persist measurement."""
        try:
            # 1. Parse and validate payload
            temperature = self._parse_payload(payload)

            # 2. Resolve sensor by exact mqtt_topic match
            async with self.session_factory() as session:
                await self._persist_measurement(
                    session, topic, temperature
                )
                await session.commit()

        except Exception:
            logger.exception("Failed to process MQTT message topic=%s", topic)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        mqtt_topic: str,
        temperature: float,
    ) -> None:
        """Look up the sensor by its exact mqtt_topic, then persist the measurement."""
        stmt = select(Sensor).where(Sensor.mqtt_topic == mqtt_topic)
        result = await session.execute(stmt)
        sensor = result.scalar_one_or_none()

        if sensor is None:
            logger.warning(
                "Unknown MQTT topic — topic=%s — ignoring message",
                mqtt_topic,
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
            "Measurement saved — topic=%s temp=%.2f",
            mqtt_topic,
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
                "mqtt_topic": sensor.mqtt_topic,
                "current_temperature": temperature,
                "last_message_at": now.isoformat(),
            },
        )