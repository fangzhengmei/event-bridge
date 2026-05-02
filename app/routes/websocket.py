"""WebSocket endpoint backed by the in-process event bus."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.event_bus import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
