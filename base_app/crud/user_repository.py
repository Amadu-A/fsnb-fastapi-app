# /base_app/crud/user_repository.py
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.logging import get_logger
from base_app.core.models import User, Profile, Permission
from base_app.core.schemas.user import UserCreate
from base_app.core.security import hash_password

log = get_logger("repo.user")


class UserRepository:
    """
    DI-friendly репозиторий: операции с User и связанными сущностями.
    """

    async def get_by_email(self, db: AsyncSession, *, email: str) -> Optional[User]:
        log.info({"event": "get_by_email", "email": email})
        res = await db.execute(select(User).where(User.email == email))
        return res.scalar_one_or_none()

    async def get_profile_by_user_id(self, db: AsyncSession, *, user_id: int) -> Optional[Profile]:
        res = await db.execute(select(Profile).where(Profile.user_id == user_id))
        return res.scalar_one_or_none()

    async def create_user_with_profile_and_permission(
        self,
        db: AsyncSession,
        *,
        email: str,
        hashed_password: str,
    ) -> User:
        """
        Атомарно создаёт:
          - User
          - Profile (1:1)
          - Permission (базовая роль is_user=True)
        Коммит снаружи.
        """
        log.info({"event": "create_user_start", "email": email})

        user = User(email=email, hashed_password=hashed_password, is_active=True)
        db.add(user)
        await db.flush()  # появится user.id

        log.info({"event": "create_profile", "user_id": user.id})
        profile = Profile(user_id=user.id, email=email, verification=False)
        db.add(profile)
        await db.flush()  # появится profile.id

        log.info({"event": "create_permission", "profile_id": profile.id})
        perm = Permission(
            profile_id=profile.id,
            is_superadmin=False,
            is_admin=False,
            is_staff=False,
            is_updater=False,
            is_reader=False,
            is_user=True,
        )
        db.add(perm)
        await db.flush()

        log.info({"event": "create_user_done", "user_id": user.id})
        return user

    async def update_profile(self, db: AsyncSession, *, profile_id: int, **fields) -> None:
        """
        Обновляет произвольные поля профиля по id.
        Пример fields: {"nickname": "...", "session": "...", "avatar": "..."}.
        """
        if not fields:
            return
        await db.execute(
            update(Profile)
            .where(Profile.id == profile_id)
            .values(**fields)
        )


# --- Функции-обёртки для удобного использования из API / views ---
async def get_all_users(db: AsyncSession) -> Sequence[User]:
    """
    Вернёт всех пользователей в порядке убывания id.
    """
    log.info({"event": "list_users"})
    res = await db.execute(select(User).order_by(User.id.desc()))
    return list(res.scalars())


async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
    """
    Создать пользователя по схеме UserCreate (email+password).
    """
    repo = UserRepository()
    email = user_create.email.strip().lower()
    if await repo.get_by_email(db, email=email):
        log.info({"event": "create_user_exists", "email": email})
        raise ValueError("email_already_exists")

    user = await repo.create_user_with_profile_and_permission(
        db,
        email=email,
        hashed_password=hash_password(user_create.password),
    )
    return user
