# /base_app/core/security.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import jwt
# Берём прямой хешер bcrypt_sha256 — он сначала делает SHA-256,
# поэтому ограничение bcrypt в 72 байта не срабатывает.
from passlib.hash import bcrypt_sha256

from base_app.core.config import settings


def hash_password(password: str) -> str:
    """
    Возвращает хэш пароля с использованием bcrypt_sha256.
    bcrypt_sha256 предварительно SHA-256-хеширует пароль,
    снимая лимит 72 байт у классического bcrypt.
    """
    return bcrypt_sha256.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие пароля и хэша.
    """
    if not hashed_password:
        return False
    return bcrypt_sha256.verify(plain_password, hashed_password)


def create_access_token(
    *,
    subject: int | str,
    expires_minutes: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Создаёт JWT (Bearer). По умолчанию TTL берём из settings.auth.access_token_minutes.
    """
    to_encode: Dict[str, Any] = {"sub": str(subject)}
    if extra:
        to_encode.update(extra)
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.auth.access_token_minutes
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.auth.secret_key, algorithm=settings.auth.algorithm)
