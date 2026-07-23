from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from boltz_web.config import load_settings
from boltz_web.db import get_db
from boltz_web.models import User
from boltz_web.redis_events import redis_client

settings = load_settings()
TOKEN_TTL_SECONDS = 60 * 60 * 24


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class ProvisionUserRequest(BaseModel):
    username: str
    is_admin: bool = False


class UserOut(BaseModel):
    id: str
    is_admin: bool
    status: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    is_admin: bool


@dataclass(frozen=True)
class CurrentUser:
    id: str
    is_admin: bool


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256$210000${salt_text}${digest_text}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds_raw))
        return hmac.compare_digest(digest, expected)
    except Exception:  # noqa: BLE001
        return False


def ensure_default_admin(db: Session) -> None:
    admin = db.get(User, settings.default_admin_username)
    if admin is None:
        db.add(
            User(
                id=settings.default_admin_username,
                password_hash=hash_password(settings.default_admin_password),
                is_admin=True,
                status="active",
            ),
        )
        db.commit()
    elif admin.status != "active" or not admin.is_admin:
        admin.status = "active"
        admin.is_admin = True
        db.commit()


def create_token(user: User) -> str:
    token = secrets.token_urlsafe(32)
    redis_client.hset(
        f"boltz:session:{token}",
        mapping={"user_id": user.id, "is_admin": "1" if user.is_admin else "0"},
    )
    redis_client.expire(f"boltz:session:{token}", TOKEN_TTL_SECONDS)
    return token


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="login required")
    token = authorization.split(" ", 1)[1].strip()
    session = redis_client.hgetall(f"boltz:session:{token}")
    if not session:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    redis_client.expire(f"boltz:session:{token}", TOKEN_TTL_SECONDS)
    return CurrentUser(id=session["user_id"], is_admin=session.get("is_admin") == "1")


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="admin required")
    return current_user


def validate_username(username: str) -> str:
    normalized = username.strip()
    if not normalized or len(normalized) > 128:
        raise HTTPException(status_code=400, detail="invalid username")
    if any(char in normalized for char in "/\\\0"):
        raise HTTPException(status_code=400, detail="invalid username")
    return normalized
