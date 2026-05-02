"""In-process event bus.

A single `ConnectionManager` instance plus a small `publish_event` helper is
enough for our single-process deployment: producers (the webhook ingest
route) call `publish_event`, which broadcasts JSON to every connected
WebSocket client.
"""

from typing import Any

from app.utils.websocket import ConnectionManager

manager = ConnectionManager()


async def publish_event(event: dict[str, Any]) -> None:
    """Fan-out a JSON-serialisable dict to all WebSocket subscribers."""
    await manager.broadcast(event)
