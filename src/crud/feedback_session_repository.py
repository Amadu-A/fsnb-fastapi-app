# path: src/crud/feedback_session_repository.py
from __future__ import annotations

from typing import Optional, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.train.models.feedback_session import FeedbackSession


class IFeedbackSessionRepository(Protocol):
    async def create(self, session: AsyncSession, source_name: str, created_by: str) -> FeedbackSession: ...
    async def close(self, session: AsyncSession, session_id: int) -> None: ...
    async def get(self, session: AsyncSession, session_id: int) -> Optional[FeedbackSession]: ...


class FeedbackSessionRepository(IFeedbackSessionRepository):
    async def create(self, session: AsyncSession, source_name: str, created_by: str) -> FeedbackSession:
        obj = FeedbackSession(source_name=source_name, created_by=created_by, status="open")
        session.add(obj)
        await session.flush()
        return obj

    async def close(self, session: AsyncSession, session_id: int) -> None:
        await session.execute(
            update(FeedbackSession).where(FeedbackSession.id == int(session_id)).values(status="closed")
        )

    async def get(self, session: AsyncSession, session_id: int) -> Optional[FeedbackSession]:
        res = await session.execute(select(FeedbackSession).where(FeedbackSession.id == int(session_id)))
        return res.scalar_one_or_none()
