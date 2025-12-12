# /src/core/services/auth_service.py
from __future__ import annotations

from datetime import datetime, timezone

from src.core.config import settings
from src.logging import get_logger
from src.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from src.crud.user_repository import UserRepository

try:
    # itsdangerous — короткие verify-ссылки
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
except Exception:  # pragma: no cover
    URLSafeTimedSerializer = None  # type: ignore

log = get_logger("service.auth")


class AuthService:
    def __init__(self) -> None:
        self.repo = UserRepository()

    # --- verify-токен для письма ---
    def _get_serializer(self) -> URLSafeTimedSerializer:
        if URLSafeTimedSerializer is None:
            raise RuntimeError("itsdangerous is not installed")
        # соль можно оставить пустой/константой, главное — один и тот же секрет
        return URLSafeTimedSerializer(settings.auth.email_verify_secret)

    def make_verify_token(self, *, uid: int, email: str) -> str:
        s = self._get_serializer()
        return s.dumps({"uid": uid, "email": email})

    def read_verify_token(self, token: str) -> dict:
        s = self._get_serializer()
        max_age = settings.auth.verify_token_ttl_hours * 3600
        try:
            data = s.loads(token, max_age=max_age)
            return dict(data)
        except SignatureExpired as e:
            raise ValueError("verify_link_expired") from e
        except BadSignature as e:
            raise ValueError("verify_link_bad") from e

    # --- Регистрация ---
    async def register_user(self, session, *, email: str, password: str) -> tuple[int, str]:
        existing = await self.repo.get_by_email(session, email=email)
        if existing:
            raise ValueError("email_already_exists")

        user = await self.repo.create_user_with_profile_and_permission(
            session,
            email=email,
            hashed_password=hash_password(password),
        )

        # Сохраняем verify-токен и метку
        token = self.make_verify_token(uid=user.id, email=email)
        user.activation_key = token
        user.activation_sent_at = datetime.now(tz=timezone.utc)
        await session.flush()

        log.info({"event": "register_success", "email": email, "user_id": user.id})
        return user.id, token

    # --- Подтверждение e-mail ---
    async def verify_email(self, session, token: str) -> int:
        data = self.read_verify_token(token)
        email = str(data.get("email", "")).strip().lower()
        uid = int(data.get("uid", 0))

        user = await self.repo.get_by_email(session, email=email)
        if not user or user.id != uid:
            raise ValueError("verify_link_bad_user")

        profile = await self.repo.get_profile_by_user_id(session, user_id=user.id)
        if profile:
            profile.verification = True

        user.activation_key = None
        await session.flush()

        log.info({"event": "verify_ok", "email": email, "uid": uid})
        return user.id

    # --- Аутентификация (для /auth/login или API) ---
    async def authenticate(self, session, *, email: str, password: str) -> str:
        user = await self.repo.get_by_email(session, email=email.strip().lower())
        if not user:
            log.info({"event": "auth_fail", "reason": "user_not_found", "email": email})
            raise ValueError("bad_credentials")

        if not verify_password(password, user.hashed_password):
            log.info({"event": "auth_fail", "reason": "wrong_password", "email": email})
            raise ValueError("bad_credentials")

        profile = await self.repo.get_profile_by_user_id(session, user_id=user.id)
        email_verified = bool(profile and profile.verification)

        if not email_verified:
            log.info({"event": "auth_warn_unverified", "email": email})

        # генерим JWT через общий helper
        token = create_access_token(
            subject=email,
            extra={
                "uid": user.id,
                "email_verified": email_verified,
            },
        )
        log.info({"event": "auth_ok", "email": email, "uid": user.id, "email_verified": email_verified})
        return token

    # --- вспомогательный метод для HTML-потока (авто-логин после регистрации) ---
    def make_access_token(self, *, email: str, uid: int, email_verified: bool) -> str:
        return create_access_token(
            subject=email,
            extra={"uid": uid, "email_verified": email_verified},
        )
