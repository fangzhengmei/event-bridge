#!/usr/bin/env python3
"""Initialize the SQLite schema for event-bridge.

The container's entrypoint also calls this implicitly via `lifespan`, but it
is exposed as a standalone script so operators can run it once on a fresh
volume without booting the full app.
"""

from sqlalchemy import inspect

from app.core import engine, settings
from app.models import Base
from app.utils.auth import ensure_admin_user


def init_database() -> None:
    print(f"Initializing SQLite schema at {settings.DATABASE_URL}")
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables: {', '.join(sorted(tables))}")

    ensure_admin_user()
    print(f"Bootstrap admin user: {settings.ADMIN_USERNAME}")
    print("Database initialization complete.")


if __name__ == "__main__":
    init_database()
