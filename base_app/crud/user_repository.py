# /base_app/crud/user_repository.py
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from base_app.core.logging import get_logger
from base_app.core.models import User, Profile, Permission
from base_app.core.schemas.user import UserCreate
from base_app.core.security import hash_password

log = get_logger("repo.user")


class UserRepository:
    """
    DI-friendly репозиторий: операции с User и связанными сущностями.
    """

    # --- Users ---

    async def get_by_email(self, session: AsyncSession, *, email: str) -> Optional[User]:
        log.info({"event": "get_by_email", "email": email})
        stmt = select(User).where(User.email == email)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_by_email_with_related(self, session: AsyncSession, *, email: str) -> Optional[User]:
        """
        Возвращает пользователя вместе с profile -> permissions (жадная загрузка),
        чтобы не ловить MissingGreenlet в шаблонах/админке.
        """
        log.info({"event": "get_by_email", "email": email})
        stmt = (
            select(User)
            .where(User.email == email)
            .options(
                selectinload(User.profile).selectinload(Profile.permissions)
            )
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def create_user_with_profile_and_permission(
        self,
        session: AsyncSession,
        *,
        email: str,
        hashed_password: str,
    ) -> User:
        """
        Атомарно создаёт:
          - User
          - Profile (1:1)
          - Permission (базовая роль is_user=True)
        Коммит — снаружи.
        """
        log.info({"event": "create_user_start", "email": email})

        user = User(email=email, hashed_password=hashed_password, is_active=True)
        session.add(user)
        await session.flush()  # появится user.id

        log.info({"event": "create_profile", "user_id": user.id})
        profile = Profile(user_id=user.id, email=email, verification=False)
        session.add(profile)
        await session.flush()  # появится profile.id

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
        session.add(perm)
        await session.flush()

        log.info({"event": "create_user_done", "user_id": user.id})
        return user

    # --- Profiles ---

    async def get_profile_by_user_id(self, session: AsyncSession, *, user_id: int) -> Optional[Profile]:
        stmt = select(Profile).where(Profile.user_id == user_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def update_profile(self, session: AsyncSession, *, profile_id: int, **fields) -> None:
        """
        Обновляет произвольные поля профиля по id.
        Пример fields: {"nickname": "...", "session": "...", "avatar": "..."}.
        Пустые строки предварительно нормализуй в вызывающем коде ('' -> None для tg_id и т.п.).
        """
        if not fields:
            return
        await session.execute(
            update(Profile)
            .where(Profile.id == profile_id)
            .values(**fields)
        )

    # --- Permissions ---

    async def get_permission_by_profile_id(
        self, session: AsyncSession, *, profile_id: int
    ) -> Optional[Permission]:
        stmt = select(Permission).where(Permission.profile_id == profile_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def create_permission(
        self, session: AsyncSession, *, profile_id: int, **flags
    ) -> Permission:
        perm = Permission(profile_id=profile_id, **flags)
        session.add(perm)
        await session.flush()
        log.info({"event": "permission_create", "profile_id": profile_id, "flags": list(flags.keys())})
        return perm

    async def update_permission(
        self, session: AsyncSession, *, permission_id: int, **flags
    ) -> None:
        if not flags:
            return
        await session.execute(
            update(Permission).where(Permission.id == permission_id).values(**flags)
        )
        log.info({"event": "permission_update", "permission_id": permission_id, "flags": list(flags.keys())})


# --- Функции-обёртки для удобного использования из views / API ---

async def get_all_users(session: AsyncSession) -> Sequence[User]:
    """
    Вернёт всех пользователей в порядке убывания id.
    Параметр назван `session`, чтобы совпадать с вызовами вида get_all_users(session=session).
    """
    log.info({"event": "list_users"})
    res = await session.execute(select(User).order_by(User.id.desc()))
    return list(res.scalars())


async def create_user(session: AsyncSession, user_create: UserCreate) -> User:
    """
    Создать пользователя по схеме UserCreate (email+password).
    """
    repo = UserRepository()
    email = user_create.email.strip().lower()

    if await repo.get_by_email(session, email=email):
        log.info({"event": "create_user_exists", "email": email})
        raise ValueError("email_already_exists")

    user = await repo.create_user_with_profile_and_permission(
        session,
        email=email,
        hashed_password=hash_password(user_create.password),
    )
    return user
