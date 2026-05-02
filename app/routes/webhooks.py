"""HTTP routes for managing and ingesting webhooks."""

import json
import random
import string
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core import SessionLocal
from app.models import DeadLetter, Destination, Webhook, WebhookRequest
from app.services.event_bus import publish_event
from app.services.forwarder import submit_request_id
from app.utils.auth import get_current_user, require_auth

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _random_slug(length: int = 10) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = SessionLocal()
    try:
        webhooks = (
            db.query(Webhook).filter(Webhook.user_id == user["id"]).all()
        )
        for webhook in webhooks:
            webhook.request_count = (
                db.query(WebhookRequest)
                .filter(WebhookRequest.webhook_id == webhook.id)
                .count()
            )
            last = (
                db.query(WebhookRequest.timestamp)
                .filter(WebhookRequest.webhook_id == webhook.id)
                .order_by(WebhookRequest.timestamp.desc())
                .first()
            )
            webhook.last_activity = last[0] if last else None
        return templates.TemplateResponse(
            request,
            "index.html",
            {"webhooks": webhooks, "user": user},
        )
    finally:
        db.close()


@router.post("/add_webhook")
async def add_webhook(request: Request):
    user = require_auth(request)
    data = await request.json()
    webhook_name = data.get("name")
    if not webhook_name:
        raise HTTPException(status_code=400, detail="name is required")

    slug = _random_slug()
    webhook_url = f"{request.url.scheme}://{request.url.netloc}/{slug}"

    db = SessionLocal()
    try:
        new_webhook = Webhook(
            url=slug, name=webhook_name, user_id=user["id"]
        )
        db.add(new_webhook)
        db.commit()
        return JSONResponse(
            {"url": webhook_url, "name": webhook_name}, status_code=201
        )
    finally:
        db.close()


@router.post("/pause")
async def pause_webhook(request: Request):
    user = require_auth(request)
    data = await request.json()
    webhook_url = data["url"]

    db = SessionLocal()
    try:
        webhook = (
            db.query(Webhook)
            .filter(
                Webhook.url == webhook_url, Webhook.user_id == user["id"]
            )
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        webhook.status = not webhook.status
        db.commit()
        return JSONResponse(
            {
                "message": "Webhook status updated successfully",
                "status": webhook.status,
            },
            status_code=200,
        )
    finally:
        db.close()


@router.post("/delete")
async def delete_webhook(request: Request):
    user = require_auth(request)
    data = await request.json()
    webhook_url = data["url"]

    db = SessionLocal()
    try:
        webhook = (
            db.query(Webhook)
            .filter(
                Webhook.url == webhook_url, Webhook.user_id == user["id"]
            )
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        db.query(WebhookRequest).filter(
            WebhookRequest.webhook_id == webhook.id
        ).delete()
        db.delete(webhook)
        db.commit()
        return JSONResponse(
            {"message": "Webhook deleted successfully"}, status_code=200
        )
    finally:
        db.close()


@router.post("/delete_request")
async def delete_webhook_request(request: Request):
    user = require_auth(request)
    data = await request.json()
    request_id = data["id"]

    db = SessionLocal()
    try:
        req = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.id == request_id)
            .first()
        )
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        webhook = (
            db.query(Webhook)
            .filter(
                Webhook.id == req.webhook_id, Webhook.user_id == user["id"]
            )
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=403, detail="Forbidden")
        db.delete(req)
        db.commit()
        return JSONResponse(
            {"message": "Webhook request deleted successfully"},
            status_code=200,
        )
    finally:
        db.close()


@router.post("/webhooks/delete_all")
async def delete_all_webhook_requests(request: Request):
    user = require_auth(request)
    data = await request.json()
    webhook_url = data["webhook_id"]

    db = SessionLocal()
    try:
        webhook = (
            db.query(Webhook)
            .filter(
                Webhook.url == webhook_url, Webhook.user_id == user["id"]
            )
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        deleted = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.webhook_id == webhook.id)
            .delete()
        )
        db.commit()
        return JSONResponse(
            {"message": f"Successfully deleted {deleted} webhook requests."},
            status_code=200,
        )
    finally:
        db.close()


@router.get("/settings/{webhook_id}", response_class=HTMLResponse)
async def webhook_settings_get(webhook_id: str, request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = SessionLocal()
    try:
        webhook = (
            db.query(Webhook)
            .filter(Webhook.url == webhook_id, Webhook.user_id == user["id"])
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        destinations = ", ".join(d.url for d in webhook.destinations)
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "webhook": webhook,
                "destinations": destinations,
                "user": user,
            },
        )
    finally:
        db.close()


@router.post("/settings/{webhook_id}")
async def webhook_settings_post(webhook_id: str, request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = SessionLocal()
    try:
        webhook = (
            db.query(Webhook)
            .filter(Webhook.url == webhook_id, Webhook.user_id == user["id"])
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        form_data = await request.form()
        db.query(Destination).filter(
            Destination.webhook_id == webhook.id
        ).delete()

        raw_urls = form_data.get("destination_urls", "")
        urls = raw_urls.replace("\n", ",").replace("\r", "").split(",")
        for url in urls:
            url = url.strip()
            if url:
                db.add(Destination(url=url, webhook_id=webhook.id))

        webhook.transformation_script = form_data.get("transformation_script")
        db.commit()
        return RedirectResponse(
            url=f"/settings/{webhook_id}?saved=true", status_code=303
        )
    finally:
        db.close()


@router.post("/{path:path}")
async def handle_webhook(path: str, request: Request):
    """Public ingest endpoint. No authentication."""
    db = SessionLocal()
    try:
        webhook = db.query(Webhook).filter(Webhook.url == path).first()
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        if not webhook.status:
            return JSONResponse(
                {"message": "Webhook is paused"}, status_code=200
            )

        headers = dict(request.headers)
        query_params = dict(request.query_params)
        body = await request.body()
        body_text = body.decode("utf-8", errors="replace") if body else ""

        new_request = WebhookRequest(
            webhook_id=webhook.id,
            headers=json.dumps(headers),
            body=body_text,
            query_params=json.dumps(query_params) if query_params else None,
            timestamp=datetime.utcnow(),
        )
        db.add(new_request)
        db.commit()
        db.refresh(new_request)

        request_id = new_request.id
        webhook_id = webhook.id
        webhook_slug = webhook.url
    finally:
        db.close()

    submit_request_id(request_id)

    try:
        await publish_event(
            {
                "type": "new_webhook_request",
                "webhook_id": webhook_id,
                "webhook_url": webhook_slug,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
                "body_length": len(body_text),
            }
        )
    except Exception:
        pass

    return JSONResponse(
        {
            "message": "Webhook received and queued for processing",
            "request_id": request_id,
            "status": "queued",
        },
        status_code=202,
    )


@router.get("/{path}")
async def show_webhook(path: str, request: Request):
    if path == "favicon.ico":
        raise HTTPException(status_code=404, detail="Not found")

    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = SessionLocal()
    try:
        webhook = (
            db.query(Webhook)
            .filter(Webhook.url == path, Webhook.user_id == user["id"])
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        total_requests = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.webhook_id == webhook.id)
            .count()
        )
        requests_list = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.webhook_id == webhook.id)
            .order_by(WebhookRequest.timestamp.desc())
            .limit(100)
            .all()
        )
        for req in requests_list:
            try:
                req.headers = json.loads(req.headers)
            except json.JSONDecodeError:
                req.headers = {}

        return templates.TemplateResponse(
            request,
            "webhook_details.html",
            {
                "webhook": webhook,
                "requests": requests_list,
                "total_requests": total_requests,
                "user": user,
            },
        )
    finally:
        db.close()


@router.get("/api/webhook/{webhook_url}/requests")
async def get_webhook_requests(
    webhook_url: str, request: Request, offset: int = 0, limit: int = 100
):
    user = require_auth(request)

    db = SessionLocal()
    try:
        webhook = (
            db.query(Webhook)
            .filter(
                Webhook.url == webhook_url, Webhook.user_id == user["id"]
            )
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        total = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.webhook_id == webhook.id)
            .count()
        )
        rows = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.webhook_id == webhook.id)
            .order_by(WebhookRequest.timestamp.desc())
            .offset(offset)
            .limit(min(limit, 100))
            .all()
        )
        return JSONResponse(
            {
                "requests": [
                    {
                        "id": req.id,
                        "timestamp": (
                            req.timestamp.isoformat() + "Z"
                            if req.timestamp
                            else None
                        ),
                        "body_length": len(req.body) if req.body else 0,
                    }
                    for req in rows
                ],
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(rows) < total,
            }
        )
    finally:
        db.close()


@router.get("/webhook/request/{request_id}")
async def show_request(request_id: int, request: Request):
    user = require_auth(request)

    db = SessionLocal()
    try:
        req = (
            db.query(WebhookRequest)
            .filter(WebhookRequest.id == request_id)
            .first()
        )
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        webhook = (
            db.query(Webhook)
            .filter(
                Webhook.id == req.webhook_id, Webhook.user_id == user["id"]
            )
            .first()
        )
        if not webhook:
            raise HTTPException(status_code=403, detail="Forbidden")
        return JSONResponse(
            {
                "headers": json.loads(req.headers) if req.headers else {},
                "body": req.body,
                "query_params": (
                    json.loads(req.query_params) if req.query_params else {}
                ),
                "timestamp": (
                    req.timestamp.isoformat() if req.timestamp else None
                ),
            }
        )
    finally:
        db.close()


@router.get("/api/dead_letters")
async def list_dead_letters(request: Request, limit: int = 100):
    """Return recent dead-letter rows for the authenticated user."""
    user = require_auth(request)

    db = SessionLocal()
    try:
        rows = (
            db.query(DeadLetter)
            .join(Webhook, Webhook.id == DeadLetter.webhook_id)
            .filter(Webhook.user_id == user["id"])
            .order_by(DeadLetter.created_at.desc())
            .limit(min(limit, 500))
            .all()
        )
        return JSONResponse(
            {
                "dead_letters": [
                    {
                        "id": r.id,
                        "webhook_id": r.webhook_id,
                        "request_id": r.request_id,
                        "destination_url": r.destination_url,
                        "attempts": r.attempts,
                        "last_error": r.last_error,
                        "created_at": (
                            r.created_at.isoformat()
                            if r.created_at
                            else None
                        ),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
        )
    finally:
        db.close()
