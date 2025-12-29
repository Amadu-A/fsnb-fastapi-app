# path: src/crud/feedback_session_repository.py
from __future__ import annotations

from typing import Optional, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.train.models.feedback_row import FeedbackRow
from src.train.models.feedback_session import FeedbackSession


class IFeedbackSessionRepository(Protocol):
    async def create(self, session: AsyncSession, source_name: str, created_by: str) -> FeedbackSession: ...
    async def close(self, session: AsyncSession, session_id: int) -> None: ...
    async def get(self, session: AsyncSession, session_id: int) -> Optional[FeedbackSession]: ...
    async def get_with_rows_and_candidates(
        self, session: AsyncSession, session_id: int
    ) -> Optional[FeedbackSession]: ...


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

    async def get_with_rows_and_candidates(
        self, session: AsyncSession, session_id: int
    ) -> Optional[FeedbackSession]:
        stmt = (
            select(FeedbackSession)
            .where(FeedbackSession.id == int(session_id))
            .options(
                selectinload(FeedbackSession.rows).selectinload(FeedbackRow.candidates),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()