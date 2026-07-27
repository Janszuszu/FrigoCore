"""FrigoCore — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session_factory, init_db
from app.mqtt.client import MQTTEngine
from app.services.alarm_engine import AlarmEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engines — instantiated once at module level, started/stopped in lifespan
# ---------------------------------------------------------------------------
mqtt_engine = MQTTEngine(settings, async_session_factory)
alarm_engine = AlarmEngine(async_session_factory)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    # Startup
    await init_db()
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

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api.routes import (
    alarm_configs_router,
    alarms_router,
    measurements_router,
    notifications_router,
    objects_router,
    sensors_router,
)

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
