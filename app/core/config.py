"""Application settings loaded from environment / .env."""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime configuration. Read once at import time."""

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./data/event_bridge.db"
    )

    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    DEBUG: bool = _env_bool("DEBUG", False)

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "change-this-secret-key-in-production"
    )

    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    JWT_COOKIE_NAME: str = os.getenv("JWT_COOKIE_NAME", "event_bridge_session")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))
    JWT_ALGORITHM: str = "HS256"

    FORWARD_MAX_ATTEMPTS: int = int(os.getenv("FORWARD_MAX_ATTEMPTS", "5"))
    FORWARD_BASE_BACKOFF_SECONDS: float = float(
        os.getenv("FORWARD_BASE_BACKOFF_SECONDS", "1.0")
    )
    FORWARD_HTTP_TIMEOUT_SECONDS: float = float(
        os.getenv("FORWARD_HTTP_TIMEOUT_SECONDS", "10.0")
    )

    WEBHOOK_RETENTION_DAYS: int = int(os.getenv("WEBHOOK_RETENTION_DAYS", "30"))


settings = Settings()
