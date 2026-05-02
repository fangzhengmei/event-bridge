"""In-process forwarder.

Every accepted webhook request is enqueued onto a single in-memory
`asyncio.Queue`. A background task drains the queue, runs the optional
RestrictedPython transformation script and POSTs the result to each
configured destination URL with exponential backoff retries.

If a destination cannot be reached after `FORWARD_MAX_ATTEMPTS` attempts,
the failure is recorded in the `dead_letter` table for manual inspection.
"""

from __future__ import annotations

import asyncio
import csv as _csv
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.Eval import (
    default_guarded_getiter,
    default_guarded_getitem,
)
from RestrictedPython.Guards import (
    full_write_guard,
    safer_getattr,
)
from sqlalchemy.orm import joinedload

from app.core import SessionLocal, settings
from app.models import DeadLetter, Webhook, WebhookRequest

logger = logging.getLogger("event_bridge.forwarder")

queue: "asyncio.Queue[int]" = asyncio.Queue()


def submit_request_id(request_id: int) -> None:
    """Hand a freshly persisted request_id off to the forwarder loop.

    Called from FastAPI route handlers, which are themselves running in the
    asyncio loop, so `put_nowait` is safe.
    """
    queue.put_nowait(request_id)


async def forwarder_loop() -> None:
    """Long-running background task started by FastAPI's lifespan."""
    timeout = httpx.Timeout(settings.FORWARD_HTTP_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            request_id = await queue.get()
            try:
                await _process_request(client, request_id)
            except Exception:  # pragma: no cover - last-resort guard
                logger.exception("forwarder crashed on request %s", request_id)
            finally:
                queue.task_done()


async def _process_request(client: httpx.AsyncClient, request_id: int) -> None:
    snapshot = _load_snapshot(request_id)
    if snapshot is None:
        logger.warning("request %s vanished before forwarding", request_id)
        return

    transformed_body = _apply_transform(
        snapshot["body"], snapshot["transformation_script"]
    )

    forward_headers = _strip_hop_headers(snapshot["headers"])

    for dest_url in snapshot["destinations"]:
        await _deliver_with_retry(
            client=client,
            webhook_id=snapshot["webhook_id"],
            request_id=request_id,
            dest_url=dest_url,
            body=transformed_body,
            headers=forward_headers,
        )


def _load_snapshot(request_id: int) -> Optional[dict]:
    """Read everything the forwarder needs in one short DB transaction."""
    db = SessionLocal()
    try:
        req = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.id == request_id)
            .first()
        )
        if not req:
            return None
        webhook = (
            db.query(Webhook)
            .options(joinedload(Webhook.destinations))
            .filter(Webhook.id == req.webhook_id)
            .first()
        )
        if not webhook:
            return None
        try:
            headers = json.loads(req.headers) if req.headers else {}
        except json.JSONDecodeError:
            headers = {}
        return {
            "webhook_id": webhook.id,
            "transformation_script": webhook.transformation_script,
            "destinations": [d.url for d in webhook.destinations],
            "headers": headers,
            "body": req.body or "",
        }
    finally:
        db.close()


def _strip_hop_headers(headers: dict) -> dict:
    drop = {"host", "content-length", "connection"}
    cleaned = {k: v for k, v in headers.items() if k.lower() not in drop}
    if not any(k.lower() == "content-type" for k in cleaned):
        cleaned["Content-Type"] = "application/json"
    return cleaned


def _apply_transform(body: str, script: Optional[str]) -> str:
    if not script or not script.strip():
        return body
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        # Non-JSON payload: skip transform, forward as-is.
        return body
    try:
        script_globals = safe_globals.copy()
        script_globals.update({"json": json, "time": time, "csv": _csv})
        script_globals["_write_"] = full_write_guard
        script_globals["_getitem_"] = default_guarded_getitem
        script_globals["_getiter_"] = default_guarded_getiter
        script_globals["_getattr_"] = safer_getattr
        byte_code = compile_restricted(script, "<transform>", "exec")
        local_env: dict = {}
        exec(byte_code, script_globals, local_env)  # noqa: S102
        transform_func = local_env.get("transform")
        if not callable(transform_func):
            return body
        return json.dumps(transform_func(data))
    except Exception as exc:
        logger.warning("transform failed: %s", exc)
        return body


async def _deliver_with_retry(
    *,
    client: httpx.AsyncClient,
    webhook_id: int,
    request_id: int,
    dest_url: str,
    body: str,
    headers: dict,
) -> None:
    last_error: Optional[str] = None
    for attempt in range(1, settings.FORWARD_MAX_ATTEMPTS + 1):
        try:
            response = await client.post(dest_url, content=body, headers=headers)
            if response.status_code < 500:
                logger.info(
                    "forwarded request=%s -> %s status=%s",
                    request_id, dest_url, response.status_code,
                )
                return
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except (httpx.HTTPError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < settings.FORWARD_MAX_ATTEMPTS:
            backoff = settings.FORWARD_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)
    _persist_dead_letter(
        webhook_id=webhook_id,
        request_id=request_id,
        dest_url=dest_url,
        attempts=settings.FORWARD_MAX_ATTEMPTS,
        last_error=last_error or "unknown error",
    )


def _persist_dead_letter(
    *,
    webhook_id: int,
    request_id: int,
    dest_url: str,
    attempts: int,
    last_error: str,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            DeadLetter(
                webhook_id=webhook_id,
                request_id=request_id,
                destination_url=dest_url,
                attempts=attempts,
                last_error=last_error[:2000],
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to persist dead letter")
    finally:
        db.close()


async def retention_sweep_loop() -> None:
    """Once per hour, prune `webhook_request` rows older than the retention horizon."""
    while True:
        try:
            cutoff = datetime.utcnow() - timedelta(
                days=settings.WEBHOOK_RETENTION_DAYS
            )
            db = SessionLocal()
            try:
                deleted = (
                    db.query(WebhookRequest)
                    .filter(WebhookRequest.timestamp < cutoff)
                    .delete(synchronize_session=False)
                )
                if deleted:
                    db.commit()
                    logger.info("retention sweep removed %s rows", deleted)
                else:
                    db.rollback()
            finally:
                db.close()
        except Exception:  # pragma: no cover
            logger.exception("retention sweep failed")
        await asyncio.sleep(3600)
