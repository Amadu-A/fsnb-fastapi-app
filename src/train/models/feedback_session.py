# path: src/train/models/feedback_session.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.models.base import Base


class FeedbackSession(Base):
    """
    Таблица feedback_sessions — “сессия разметки”.

    Зачем нужна:
    - группирует пачку строк спецификации под одним источником/контекстом;
    - удобно фильтровать выгрузки датасета: по source_name, периоду, статусу open/closed;
    - помогает трассировать “кто и когда разметил” и какие данные ушли в обучение.

    Пример:
    source_name = "РД_объект_А_декабрь_2025"
    created_by  = "user:admin@company.ru"
    status      = "open" / "closed"
    """

    __tablename__ = "feedback_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    source_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # open|closed (пока text — проще, чем enum; можно ужесточить позже)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")

    # Связи
    rows = relationship(
        "FeedbackRow",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
