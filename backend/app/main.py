"""FrigoCore — FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    # Startup: create tables
    await init_db()
    # TODO: Start MQTT listener
    yield
    # Shutdown: cleanup
    # TODO: Stop MQTT listener


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


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME, "environment": settings.ENVIRONMENT}


# ---------------------------------------------------------------------------
# Placeholder routers (to be implemented in subsequent iterations)
# ---------------------------------------------------------------------------
# app.include_router(objects.router, prefix="/api/v1/objects", tags=["objects"])
# app.include_router(sensors.router, prefix="/api/v1/sensors", tags=["sensors"])
# app.include_router(alarms.router, prefix="/api/v1/alarms", tags=["alarms"])
# app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
# app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
# app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])