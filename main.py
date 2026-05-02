"""event-bridge entry point.

Single-process FastAPI app: HTTP routes + WebSocket + a background forwarder
coroutine + a hourly retention sweep, all running in the same uvicorn worker.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.core import settings
from app.routes import auth_router, webhooks_router, websocket_router
from app.services.forwarder import forwarder_loop, retention_sweep_loop
from app.utils.auth import ensure_admin_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("event_bridge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core import engine
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    ensure_admin_user()

    forwarder_task = asyncio.create_task(
        forwarder_loop(), name="forwarder_loop"
    )
    retention_task = asyncio.create_task(
        retention_sweep_loop(), name="retention_sweep_loop"
    )
    logger.info(
        "event-bridge started on %s:%s", settings.APP_HOST, settings.APP_PORT
    )

    try:
        yield
    finally:
        for task in (forwarder_task, retention_task):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("event-bridge shutdown complete")


app = FastAPI(
    title="event-bridge",
    description="Self-hosted inbound webhook gateway with retry and DLQ.",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})


app.include_router(auth_router, tags=["auth"])
app.include_router(webhooks_router, tags=["webhooks"])
app.include_router(websocket_router, tags=["websocket"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )
