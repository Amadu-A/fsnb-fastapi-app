# /src/core/security.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt, JWTError
from passlib.hash import bcrypt_sha256

from src.core.config import settings


def hash_password(password: str) -> str:
    """Хэш пароля через bcrypt_sha256 (снимает лимит 72 байта у bcrypt)."""
    return bcrypt_sha256.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля."""
    if not hashed_password:
        return False
    return bcrypt_sha256.verify(plain_password, hashed_password)


def create_access_token(
    *,
    subject: int | str,
    expires_minutes: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Создаёт JWT (Bearer)."""
    to_encode: Dict[str, Any] = {"sub": str(subject)}
    if extra:
        to_encode.update(extra)
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.auth.access_token_minutes
    )
    to_encode["exp"] = int(expire.timestamp())
    return jwt.encode(to_encode, settings.auth.secret_key, algorithm=settings.auth.algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Декодирует и валидирует JWT. Бросает jose.JWTError при неверной подписи/просрочке.
    """
    payload = jwt.decode(token, settings.auth.secret_key, algorithms=[settings.auth.algorithm])
    # payload уже проверен по exp
    return dict(payload)
