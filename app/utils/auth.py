"""JWT-cookie based local authentication helpers.

The whole identity model is intentionally minimal: a single `user` table with
`username` + bcrypt `password_hash`. The signed JWT carries `sub` (user id)
and `username`, lives in an HttpOnly cookie, and is verified on every
request.
"""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request
from jose import JWTError, jwt

from app.core import SessionLocal, settings
from app.models import User


# bcrypt only hashes the first 72 bytes; truncate explicitly so a long
# password produces a deterministic hash and verifies cleanly.
def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, username: str) -> str:
    expires = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expires,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    sub = payload.get("sub")
    username = payload.get("username")
    if not sub or not username:
        return None
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        return None
    return {"id": user_id, "username": username}


def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(settings.JWT_COOKIE_NAME)
    if not token:
        return None
    return _decode_token(token)


def require_auth(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def authenticate(username: str, password: str) -> Optional[dict]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            return None
        user.last_login = datetime.utcnow()
        db.commit()
        return {"id": user.id, "username": user.username}
    finally:
        db.close()


def ensure_admin_user() -> None:
    """Create the bootstrap admin account if no user exists yet."""
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        admin = User(
            username=settings.ADMIN_USERNAME,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow(),
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()
