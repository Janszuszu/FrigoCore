"""FrigoCore — WebSocket manager for real-time events.

Broadcasts events to connected clients:
  - measurement.created
  - sensor.updated
  - sensor.offline
  - alarm.pending
  - alarm.triggered
  - alarm.acknowledged
  - alarm.resolved
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ws_router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected — total=%d", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.remove(websocket)
        logger.info("WebSocket client disconnected — total=%d", len(self._connections))

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        """Send a JSON event to all connected clients."""
        if not self._connections:
            return

        message = json.dumps({"event": event, "data": payload}, default=str)

        dead: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)

        for conn in dead:
            try:
                self._connections.remove(conn)
            except ValueError:
                pass


# Singleton
manager = ConnectionManager()


@ws_router.websocket("/events")
async def websocket_events(websocket: WebSocket) -> None:
    """WebSocket endpoint — clients connect here to receive live events."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive — ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)