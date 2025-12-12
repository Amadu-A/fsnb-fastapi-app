# /src/core/email_tokens.py
from __future__ import annotations

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from .config import settings


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        secret_key=settings.auth.email_verify_secret,
        salt="email-verify",
    )


def make_email_token(user_id: int) -> str:
    return _serializer().dumps({"uid": user_id})


def read_email_token(token: str) -> dict:
    max_age = settings.auth.verify_token_ttl_hours * 3600
    data = _serializer().loads(token, max_age=max_age)
    return data
