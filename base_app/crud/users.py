# /base_app/crud/users.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.models.user import User


async def get_all_users(session: AsyncSession) -> list[User]:
    stmt = select(User).order_by(User.id.desc())
    res = await session.scalars(stmt)
    return list(res)


async def get_user_by_email(session: AsyncSession, *, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    res = await session.scalars(stmt)
    return res.first()
