"""SQLite (only) engine and session factory.

The whole gateway is designed for a single-process deployment, so we keep the
storage layer deliberately small: synchronous SQLAlchemy + SQLite in WAL mode,
opened with a generous busy timeout so concurrent FastAPI workers don't trip
on each other.
"""

import os
from urllib.parse import urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .config import settings

if not settings.DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "event-bridge only supports SQLite. "
        f"Got DATABASE_URL={settings.DATABASE_URL!r}"
    )

# Make sure the directory for the SQLite file exists. SQLAlchemy / sqlite
# happily creates the file but not its parent directory.
_path_part = urlparse(settings.DATABASE_URL).path
if _path_part:
    _db_path = _path_part.lstrip("/")
    _db_dir = os.path.dirname(_db_path)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: yield a session and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
