# path: src/core/services/auth_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.app_logging import get_logger
from src.core.config import settings
from src.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from src.crud.user_repository import IUserRepository, UserRepository

try:
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
except Exception:  # pragma: no cover
    URLSafeTimedSerializer = None  # type: ignore


log = get_logger("service.auth")


class AuthService:
    """
    Сервис авторизации/регистрации.

    Важно:
    - Repo приходит через DI (или создаётся по умолчанию),
      чтобы сервис не зависел от конкретной реализации.
    - DB-операции выполняются через репозиторий.
    """

    def __init__(self, repo: Optional[IUserRepository] = None) -> None:
        self.repo: IUserRepository = repo or UserRepository()

    # --- verify-токен для письма ---
    def _get_serializer(self) -> URLSafeTimedSerializer:
        if URLSafeTimedSerializer is None:
            raise RuntimeError("itsdangerous is not installed")
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
        email_norm = email.strip().lower()

        existing = await self.repo.get_by_email(session, email=email_norm)
        if existing:
            raise ValueError("email_already_exists")

        user = await self.repo.create_user_with_profile_and_permission(
            session,
            email=email_norm,
            hashed_password=hash_password(password),
        )

        token = self.make_verify_token(uid=int(user.id), email=email_norm)

        # ✅ не трогаем ORM-поля напрямую — только через repo
        await self.repo.set_activation_token(
            session,
            user_id=int(user.id),
            activation_key=token,
            activation_sent_at=datetime.now(tz=timezone.utc),
        )
        await session.flush()

        log.info({"event": "register_success", "email": email_norm, "user_id": int(user.id)})
        return int(user.id), token

    # --- Подтверждение e-mail ---
    async def verify_email(self, session, token: str) -> int:
        data = self.read_verify_token(token)
        email = str(data.get("email", "")).strip().lower()
        uid = int(data.get("uid", 0))

        user = await self.repo.get_by_email(session, email=email)
        if not user or int(user.id) != uid:
            raise ValueError("verify_link_bad_user")

        # ✅ одним проходом (update Profile + update User)
        await self.repo.mark_email_verified_and_clear_token(session, user_id=int(user.id))
        await session.flush()

        log.info({"event": "verify_ok", "email": email, "uid": uid})
        return int(user.id)

    # --- Аутентификация ---
    async def authenticate(self, session, *, email: str, password: str) -> str:
        email_norm = email.strip().lower()

        user = await self.repo.get_by_email(session, email=email_norm)
        if not user:
            log.info({"event": "auth_fail", "reason": "user_not_found", "email": email_norm})
            raise ValueError("bad_credentials")

        if not verify_password(password, user.hashed_password):
            log.info({"event": "auth_fail", "reason": "wrong_password", "email": email_norm})
            raise ValueError("bad_credentials")

        profile = await self.repo.get_profile_by_user_id(session, user_id=int(user.id))
        email_verified = bool(profile and profile.verification)

        if not email_verified:
            log.info({"event": "auth_warn_unverified", "email": email_norm})

        token = create_access_token(
            subject=email_norm,
            extra={"uid": int(user.id), "email_verified": email_verified},
        )
        log.info({"event": "auth_ok", "email": email_norm, "uid": int(user.id), "email_verified": email_verified})
        return token

    # --- для HTML-потока (авто-логин после регистрации) ---
    def make_access_token(self, *, email: str, uid: int, email_verified: bool) -> str:
        return create_access_token(
            subject=email,
            extra={"uid": uid, "email_verified": email_verified},
        )
