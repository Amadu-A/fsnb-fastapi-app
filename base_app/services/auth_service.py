# /base_app/services/auth_service.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.logging import get_logger
from base_app.core.models.user import User
from base_app.core.models.profile import Profile
from base_app.core.models.permission import Permission
from base_app.core.security import hash_password, verify_password, create_access_token
from base_app.core.email_tokens import make_email_token

log = get_logger("auth_service")


class AuthService:
    """
    Полный цикл: регистрация → создание User/Profile/Permission → токен верификации → логин (JWT).
    """

    async def register_user(self, session: AsyncSession, *, email: str, password: str) -> tuple[int, str]:
        # Проверяем наличие пользователя
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

        # Создаём User
        u = User(
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            activation_key=None,
            activation_sent_at=datetime.now(UTC),
        )
        session.add(u)
        await session.flush()  # получим u.id

        # Создаём Profile + базовые права
        p = Profile(user_id=u.id, email=email, verification=False)
        p.permissions = [Permission(is_user=True)]
        session.add(p)
        await session.flush()

        # Готовим токен для письма
        token = make_email_token(u.id)
        return u.id, token

    async def authenticate(self, session: AsyncSession, *, email: str, password: str) -> str:
        res = await session.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()
        if not user or not user.hashed_password:
            # либо пользователя нет, либо у старой записи нет хэша — не даём войти
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        return create_access_token(subject=user.id, extra={"email": user.email})
