from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from .base import Base


class User(Base):
    """Local account. No external identity provider."""

    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    webhooks = relationship(
        "Webhook", cascade="all, delete-orphan", back_populates="user"
    )
