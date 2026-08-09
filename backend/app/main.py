"""FrigoCore — FastAPI application entry point."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, init_db, get_db
from app.mqtt.client import MQTTEngine
from app.models.measurement import Measurement
from app.models.sensor import Sensor
from app.models.object import Object
from app.services.alarm_engine import AlarmEngine
from app.api.websocket import manager as ws_manager

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ---------------------------------------------------------------------------
# Engines — instantiated once at module level, started/stopped in lifespan
# ---------------------------------------------------------------------------
alarm_engine = AlarmEngine(async_session_factory)
mqtt_engine = MQTTEngine(settings, async_session_factory)


# ---------------------------------------------------------------------------
# Simulation endpoint (replaces MQTT broker for native dev)
# ---------------------------------------------------------------------------
sim_router = APIRouter()


class SimulatePayload(BaseModel):
    temperature: float


@sim_router.post("/simulate/{mqtt_topic:path}")
async def simulate_measurement(
    mqtt_topic: str,
    body: SimulatePayload,
    db: AsyncSession = Depends(get_db),
):
    """Inject a simulated MQTT measurement — same logic as MQTT client."""
    stmt = select(Sensor).where(Sensor.mqtt_topic == mqtt_topic)
    result = await db.execute(stmt)
    sensor = result.scalar_one_or_none()
    if sensor is None:
        return {"error": f"Unknown sensor for MQTT topic: {mqtt_topic}"}

    now = datetime.now(timezone.utc)
    measurement = Measurement(
        sensor_id=sensor.id,
        temperature=body.temperature,
        received_at=now,
    )
    db.add(measurement)
    sensor.current_temperature = body.temperature
    sensor.last_message_at = now
    db.add(sensor)
    await db.commit()

    logger.info("SIM measurement — topic=%s temp=%.2f", mqtt_topic, body.temperature)

    await ws_manager.broadcast(
        "measurement.created",
        {
            "id": str(measurement.id),
            "sensor_id": str(sensor.id),
            "temperature": body.temperature,
            "received_at": now.isoformat(),
        },
    )
    await ws_manager.broadcast(
        "sensor.updated",
        {
            "id": str(sensor.id),
            "mqtt_topic": sensor.mqtt_topic,
            "current_temperature": body.temperature,
            "last_message_at": now.isoformat(),
        },
    )
    return {"status": "ok", "temperature": body.temperature, "at": now.isoformat()}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    # Startup
    await init_db()
    # Auto-seed demo data if DB is empty — development only. A production
    # deployment starting against a fresh volume must not invent objects,
    # sensors and MQTT topics that no real installation has.
    if settings.ENVIRONMENT != "production":
        from app.database import async_session_factory
        from sqlalchemy import select
        from app.models.object import Object as ObjModel
        async with async_session_factory() as session:
            count = await session.scalar(select(ObjModel).limit(1))
            if count is None:
                from setup_dev import main as setup_dev_main
                await setup_dev_main()
    # Start MQTT engine first, then alarm engine
    await mqtt_engine.start()
    await alarm_engine.start()
    logger.info("FrigoCore backend is ready")
    yield
    # Shutdown
    await alarm_engine.stop()
    await mqtt_engine.stop()
    logger.info("FrigoCore backend shut down")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Cloud-native IoT Platform for Refrigeration Monitoring",
    lifespan=lifespan,
)

# CORS — explicit origin allowlist only.
# The previous configuration paired allow_origins=["*"] with
# allow_credentials=True, which browsers reject outright and which would
# otherwise let any website issue credentialed requests against this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


from app.api.routes import (
    alarm_configs_router,
    alarms_router,
    measurements_router,
    notifications_router,
    objects_router,
    sensors_router,
)
from app.api.websocket import ws_router

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME, "environment": settings.ENVIRONMENT}


# ---------------------------------------------------------------------------
# REST API routers
# ---------------------------------------------------------------------------

app.include_router(objects_router, prefix="/api/v1/objects", tags=["Objects"])
app.include_router(sensors_router, prefix="/api/v1/objects", tags=["Sensors"])
app.include_router(alarm_configs_router, prefix="/api/v1/sensors", tags=["Alarm Configs"])
app.include_router(alarms_router, prefix="/api/v1/alarms", tags=["Alarms"])
app.include_router(measurements_router, prefix="/api/v1/sensors", tags=["Measurements"])
app.include_router(notifications_router, prefix="/api/v1/objects", tags=["Notifications"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
app.include_router(sim_router, prefix="/api/v1/sim", tags=["Simulation"])
