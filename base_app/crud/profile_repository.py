# /base_app/crud/profile_repository.py
from __future__ import annotations

from typing import Protocol, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.models.profile import Profile
from base_app.core.models.permission import Permission


class IProfileRepository(Protocol):
    async def get_by_id(self, session: AsyncSession, profile_id: int) -> Optional[Profile]: ...
    async def get_by_user_id(self, session: AsyncSession, user_id: int) -> Optional[Profile]: ...
    async def create_with_defaults(self, session: AsyncSession, *, user_id: int, email: str) -> Profile: ...


class ProfileRepository(IProfileRepository):
    async def get_by_id(self, session: AsyncSession, profile_id: int) -> Optional[Profile]:
        res = await session.execute(select(Profile).where(Profile.id == profile_id))
        return res.scalar_one_or_none()

    async def get_by_user_id(self, session: AsyncSession, user_id: int) -> Optional[Profile]:
        res = await session.execute(select(Profile).where(Profile.user_id == user_id))
        return res.scalar_one_or_none()

    async def create_with_defaults(self, session: AsyncSession, *, user_id: int, email: str) -> Profile:
        profile = Profile(user_id=user_id, email=email, verification=False)
        profile.permissions = [Permission(is_user=True)]  # базовый флаг
        session.add(profile)
        await session.flush()
        return profile
