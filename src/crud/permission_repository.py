# /src/crud/permission_repository.py
from __future__ import annotations

from typing import Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.permission import Permission


class IPermissionRepository(Protocol):
    async def list_for_profile(self, session: AsyncSession, profile_id: int) -> Sequence[Permission]: ...


class PermissionRepository(IPermissionRepository):
    async def list_for_profile(self, session: AsyncSession, profile_id: int):
        res = await session.execute(select(Permission).where(Permission.profile_id == profile_id))
        return list(res.scalars())
