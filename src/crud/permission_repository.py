# path: src/crud/permission_repository.py
from __future__ import annotations

from typing import Optional, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.permission import Permission
from src.core.models.profile import Profile


class IPermissionRepository(Protocol):
    """
    DI-контракт для PermissionRepository.

    Важно:
    - Здесь только SQL к таблицам permission/profile.
    - Админка будет использовать эти методы вместо прямых select().
    """

    async def list_for_profile(self, session: AsyncSession, profile_id: int) -> Sequence[Permission]: ...

    async def get_by_profile_id(self, session: AsyncSession, profile_id: int) -> Optional[Permission]: ...

    async def get_for_user_id(self, session: AsyncSession, user_id: int) -> Optional[Permission]: ...

    async def is_admin_user(self, session: AsyncSession, user_id: int) -> bool: ...

    async def is_superadmin_user(self, session: AsyncSession, user_id: int) -> bool: ...


class PermissionRepository(IPermissionRepository):
    """
    Реализация репозитория Permission.

    Почему join через Profile:
    - Permission привязан к Profile (profile_id)
    - Profile привязан к User (user_id)
    => можем получить Permission по user_id одним запросом.
    """

    async def list_for_profile(self, session: AsyncSession, profile_id: int) -> Sequence[Permission]:
        res = await session.execute(
            select(Permission).where(Permission.profile_id == int(profile_id))
        )
        return list(res.scalars())

    async def get_by_profile_id(self, session: AsyncSession, profile_id: int) -> Optional[Permission]:
        res = await session.execute(
            select(Permission).where(Permission.profile_id == int(profile_id))
        )
        return res.scalar_one_or_none()

    async def get_for_user_id(self, session: AsyncSession, user_id: int) -> Optional[Permission]:
        """
        Возвращает Permission для пользователя по user_id одним запросом:
        Permission JOIN Profile ON Permission.profile_id = Profile.id WHERE Profile.user_id = :user_id
        """
        stmt = (
            select(Permission)
            .join(Profile, Permission.profile_id == Profile.id)
            .where(Profile.user_id == int(user_id))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def is_admin_user(self, session: AsyncSession, user_id: int) -> bool:
        perm = await self.get_for_user_id(session, user_id)
        return bool(perm and (perm.is_superadmin or perm.is_admin))

    async def is_superadmin_user(self, session: AsyncSession, user_id: int) -> bool:
        perm = await self.get_for_user_id(session, user_id)
        return bool(perm and perm.is_superadmin)
