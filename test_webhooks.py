"""Smoke tests for event-bridge.

These tests run against an isolated SQLite database (created in a temporary
directory) so they don't pollute the main data volume. They cover:

- the password hashing helpers,
- the in-process forwarder pipeline (mocking httpx),
- the dead-letter path when the destination keeps failing,
- the JSON transformation runner.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolate_database():
    """Point DATABASE_URL at a temp file before any app module is imported."""
    tmpdir = tempfile.mkdtemp(prefix="event_bridge_tests_")
    db_path = os.path.join(tmpdir, "test.db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["FORWARD_MAX_ATTEMPTS"] = "2"
    os.environ["FORWARD_BASE_BACKOFF_SECONDS"] = "0"
    yield
    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture(autouse=True)
def _reset_schema():
    """Drop and recreate tables between tests."""
    from app.core import engine
    from app.models import Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_password_round_trip():
    from app.utils.auth import hash_password, verify_password

    h = hash_password("hunter2")
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)


def test_authenticate_requires_existing_user():
    from app.utils.auth import authenticate, ensure_admin_user

    ensure_admin_user()
    assert authenticate("admin", "admin123") is not None
    assert authenticate("admin", "nope") is None
    assert authenticate("nobody", "admin123") is None


def test_transform_runs_in_sandbox():
    from app.services.forwarder import _apply_transform

    script = """
def transform(data):
    return {"sum": data["a"] + data["b"]}
"""
    out = _apply_transform(json.dumps({"a": 1, "b": 2}), script)
    assert json.loads(out) == {"sum": 3}


def test_transform_falls_back_on_bad_script():
    from app.services.forwarder import _apply_transform

    out = _apply_transform('{"a": 1}', "this is not python")
    assert out == '{"a": 1}'


def test_strip_hop_headers_drops_host():
    from app.services.forwarder import _strip_hop_headers

    cleaned = _strip_hop_headers(
        {"Host": "example.com", "Content-Length": "5", "X-Real": "v"}
    )
    assert "Host" not in cleaned and "host" not in cleaned
    assert cleaned["X-Real"] == "v"
    assert cleaned["Content-Type"] == "application/json"


@pytest.mark.anyio
async def test_dead_letter_recorded_after_max_attempts(monkeypatch):
    from app.core import SessionLocal
    from app.models import DeadLetter, Destination, User, Webhook, WebhookRequest
    from app.services import forwarder
    from app.utils.auth import hash_password

    db = SessionLocal()
    try:
        user = User(username="u1", password_hash=hash_password("x"))
        db.add(user)
        db.commit()
        db.refresh(user)

        webhook = Webhook(url="slug1", name="n", user_id=user.id)
        db.add(webhook)
        db.commit()
        db.refresh(webhook)

        db.add(Destination(url="https://nope.invalid/hook", webhook_id=webhook.id))
        req = WebhookRequest(
            webhook_id=webhook.id,
            headers="{}",
            body="{}",
            timestamp=datetime.utcnow(),
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        request_id = req.id
    finally:
        db.close()

    class _AlwaysFails:
        async def post(self, url, content=None, headers=None):
            raise OSError("simulated network error")

    await forwarder._process_request(_AlwaysFails(), request_id)

    db = SessionLocal()
    try:
        rows = db.query(DeadLetter).all()
        assert len(rows) == 1
        assert rows[0].destination_url == "https://nope.invalid/hook"
        assert rows[0].attempts == 2
    finally:
        db.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"
