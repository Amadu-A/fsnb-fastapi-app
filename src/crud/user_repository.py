# path: src/crud/user_repository.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, Sequence, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app_logging import get_logger
from src.core.models import Permission, Profile, User


log = get_logger("repo.user")


class IUserRepository(Protocol):
    # --- Users ---
    async def get_by_id(self, session: AsyncSession, *, user_id: int) -> Optional[User]: ...
    async def get_by_email(self, session: AsyncSession, *, email: str) -> Optional[User]: ...
    async def get_by_username(self, session: AsyncSession, *, username: str) -> Optional[User]: ...
    async def get_by_email_with_related(self, session: AsyncSession, *, email: str) -> Optional[User]: ...

    async def create_user_with_profile_and_permission(
        self,
        session: AsyncSession,
        *,
        email: str,
        hashed_password: str,
    ) -> User: ...

    async def update_user_fields(self, session: AsyncSession, *, user_id: int, **fields: Any) -> None: ...

    # --- Profiles ---
    async def get_profile_by_user_id(self, session: AsyncSession, *, user_id: int) -> Optional[Profile]: ...
    async def update_profile(self, session: AsyncSession, *, profile_id: int, **fields: Any) -> None: ...

    # --- Permissions ---
    async def get_permission_by_profile_id(self, session: AsyncSession, *, profile_id: int) -> Optional[Permission]: ...
    async def create_permission(self, session: AsyncSession, *, profile_id: int, **flags: Any) -> Permission: ...
    async def update_permission(self, session: AsyncSession, *, permission_id: int, **flags: Any) -> None: ...

    # --- Auth-related updates ---
    async def set_activation_token(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        activation_key: str,
        activation_sent_at: datetime,
    ) -> None: ...

    async def mark_email_verified_and_clear_token(
        self,
        session: AsyncSession,
        *,
        user_id: int,
    ) -> None: ...

    # --- Lists ---
    async def list_users(self, session: AsyncSession) -> Sequence[User]: ...


class UserRepository(IUserRepository):
    """
    Репозиторий пользователей.

    Правило проекта:
    - Все обращения к Postgres/SQLAlchemy — только здесь (src/crud/).
    """

    # --- Users ---

    async def get_by_id(self, session: AsyncSession, *, user_id: int) -> Optional[User]:
        """
        Получить пользователя по id.
        Нужен для admin views (замена session.get(User, id)).
        """
        res = await session.execute(select(User).where(User.id == int(user_id)))
        return res.scalar_one_or_none()

    async def get_by_email(self, session: AsyncSession, *, email: str) -> Optional[User]:
        log.info({"event": "get_by_email", "email": email})
        stmt = select(User).where(User.email == email)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_by_username(self, session: AsyncSession, *, username: str) -> Optional[User]:
        """
        Получить пользователя по username.
        Нужно для admin/login.
        """
        username = (username or "").strip()
        if not username:
            return None
        res = await session.execute(select(User).where(User.username == username))
        return res.scalar_one_or_none()

    async def get_by_email_with_related(self, session: AsyncSession, *, email: str) -> Optional[User]:
        log.info({"event": "get_by_email_with_related", "email": email})
        stmt = (
            select(User)
            .where(User.email == email)
            .options(selectinload(User.profile).selectinload(Profile.permissions))
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def create_user_with_profile_and_permission(
        self,
        session: AsyncSession,
        *,
        email: str,
        hashed_password: str,
    ) -> User:
        log.info({"event": "create_user_start", "email": email})

        user = User(email=email, hashed_password=hashed_password, is_active=True)
        session.add(user)
        await session.flush()

        profile = Profile(user_id=user.id, email=email, verification=False)
        session.add(profile)
        await session.flush()

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

    async def update_user_fields(self, session: AsyncSession, *, user_id: int, **fields: Any) -> None:
        """
        Универсальное обновление полей User.
        Нужен для admin edit User (замена update(User) из view).
        """
        if not fields:
            return
        await session.execute(
            update(User)
            .where(User.id == int(user_id))
            .values(**fields)
        )

    # --- Profiles ---

    async def get_profile_by_user_id(self, session: AsyncSession, *, user_id: int) -> Optional[Profile]:
        stmt = select(Profile).where(Profile.user_id == int(user_id))
        return (await session.execute(stmt)).scalar_one_or_none()

    async def update_profile(self, session: AsyncSession, *, profile_id: int, **fields: Any) -> None:
        if not fields:
            return
        await session.execute(update(Profile).where(Profile.id == int(profile_id)).values(**fields))

    # --- Permissions ---

    async def get_permission_by_profile_id(
        self, session: AsyncSession, *, profile_id: int
    ) -> Optional[Permission]:
        stmt = select(Permission).where(Permission.profile_id == int(profile_id))
        return (await session.execute(stmt)).scalar_one_or_none()

    async def create_permission(self, session: AsyncSession, *, profile_id: int, **flags: Any) -> Permission:
        perm = Permission(profile_id=profile_id, **flags)
        session.add(perm)
        await session.flush()
        log.info({"event": "permission_create", "profile_id": profile_id, "flags": list(flags.keys())})
        return perm

    async def update_permission(self, session: AsyncSession, *, permission_id: int, **flags: Any) -> None:
        if not flags:
            return
        await session.execute(update(Permission).where(Permission.id == int(permission_id)).values(**flags))
        log.info({"event": "permission_update", "permission_id": permission_id, "flags": list(flags.keys())})

    # --- Auth-related updates ---

    async def set_activation_token(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        activation_key: str,
        activation_sent_at: datetime,
    ) -> None:
        await session.execute(
            update(User)
            .where(User.id == int(user_id))
            .values(activation_key=activation_key, activation_sent_at=activation_sent_at)
        )

    async def mark_email_verified_and_clear_token(self, session: AsyncSession, *, user_id: int) -> None:
        await session.execute(
            update(Profile)
            .where(Profile.user_id == int(user_id))
            .values(verification=True)
        )
        await session.execute(
            update(User)
            .where(User.id == int(user_id))
            .values(activation_key=None)
        )

    # --- Lists ---

    async def list_users(self, session: AsyncSession) -> Sequence[User]:
        log.info({"event": "list_users"})
        res = await session.execute(select(User).order_by(User.id.desc()))
        return list(res.scalars())
