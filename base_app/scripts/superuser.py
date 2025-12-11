# /base_app/scripts/superuser.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.logging import get_logger
from base_app.core.models.user import User
from base_app.core.models.profile import Profile
from base_app.core.models.permission import Permission
from base_app.core.security import hash_password

log = get_logger("scripts.superuser")


async def create_superuser(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    email: Optional[str] = None,
) -> int:
    """
    Создаёт суперпользователя:
    - User.username = username, User.email = email or f"{username}@localhost"
    - пароль хэшируется
    - e-mail считается подтверждённым (activation_key=None)
    - создаётся Profile (verification=True, email заполняем как у user.email)
    - создаётся Permission со всеми True
    Возвращает user.id
    """
    if not username:
        raise ValueError("username is required")

    # e-mail обязателен в модели, поэтому подставим дефолт
    email_final = (email or f"{username}@localhost").strip().lower()
    password_hash = hash_password(password or "")

    # Проверка уникальности username / email
    existing_u = await session.execute(select(User).where((User.username == username) | (User.email == email_final)))
    if existing_u.scalar_one_or_none():
        raise ValueError("User with same username or email already exists")

    user = User(
        username=username,
        email=email_final,
        hashed_password=password_hash,
        is_active=True,
        activation_key=None,  # нет ключа = подтверждён
    )
    session.add(user)
    await session.flush()  # получим user.id

    profile = Profile(
        user_id=user.id,
        verification=True,
        email=email_final,
    )
    session.add(profile)
    await session.flush()  # получим profile.id

    perm = Permission(
        profile_id=profile.id,
        is_superadmin=True,
        is_admin=True,
        is_staff=True,
        is_updater=True,
        is_reader=True,
        is_user=True,
    )
    session.add(perm)

    log.info({"event": "create_superuser", "user_id": user.id, "username": username})
    return user.id
