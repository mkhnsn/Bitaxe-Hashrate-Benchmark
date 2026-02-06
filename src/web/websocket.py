"""WebSocket connection management and callbacks."""

import asyncio
import json
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel

from ..benchmark.core import BenchmarkCallbacks
from ..models import (
    BenchmarkComplete,
    BenchmarkStatus,
    ErrorMessage,
    IterationComplete,
    LogMessage,
    SampleProgress,
)


class ConnectionManager:
    """Manage WebSocket connections and broadcast messages."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any] | BaseModel) -> None:
        """Broadcast a message to all connected clients."""
        if isinstance(message, BaseModel):
            data = message.model_dump_json()
        else:
            data = json.dumps(message, default=str)

        async with self._lock:
            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(data)
                except Exception:
                    disconnected.append(connection)

            # Clean up disconnected connections
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any] | BaseModel) -> None:
        """Send a message to a specific client."""
        if isinstance(message, BaseModel):
            data = message.model_dump_json()
        else:
            data = json.dumps(message, default=str)

        try:
            await websocket.send_text(data)
        except Exception:
            await self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


def create_websocket_callbacks(
    manager: ConnectionManager,
    loop: asyncio.AbstractEventLoop,
    on_iteration_side_effect: Any = None,
) -> BenchmarkCallbacks:
    """Create benchmark callbacks that broadcast via WebSocket.

    Args:
        manager: ConnectionManager to broadcast through.
        loop: Event loop for scheduling coroutines.
        on_iteration_side_effect: Optional callable invoked after each iteration (e.g. to save summary).

    Returns:
        BenchmarkCallbacks configured for WebSocket broadcasting.
    """

    def schedule_broadcast(message: BaseModel) -> None:
        """Schedule a broadcast on the event loop."""
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)

    def on_sample(progress: SampleProgress) -> None:
        schedule_broadcast(progress)

    def on_iteration_complete(iteration: IterationComplete) -> None:
        schedule_broadcast(iteration)
        if on_iteration_side_effect:
            on_iteration_side_effect()

    def on_status_change(status: BenchmarkStatus) -> None:
        schedule_broadcast(status)

    def on_complete(complete: BenchmarkComplete) -> None:
        schedule_broadcast(complete)

    def on_error(error: ErrorMessage) -> None:
        schedule_broadcast(error)

    def on_log(log: LogMessage) -> None:
        schedule_broadcast(log)

    return BenchmarkCallbacks(
        on_sample=on_sample,
        on_iteration_complete=on_iteration_complete,
        on_status_change=on_status_change,
        on_complete=on_complete,
        on_error=on_error,
        on_log=on_log,
    )
