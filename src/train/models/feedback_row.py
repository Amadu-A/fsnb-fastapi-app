# path: src/train/models/feedback_row.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.models.base import Base


class FeedbackRow(Base):
    """
    Таблица feedback_rows — одна входная строка (позиция спецификации), которую мы сопоставляем с items.

    Зачем нужна:
    - хранит оригинальный текст (caption) и опциональные units/qty;
    - хранит norm_json (промежуточная нормализация/парсинг, если добавим);
    - хранит is_trusted — доверенность данных для обучения:
        * is_reader -> is_trusted = False (draft, “для себя”)
        * editor    -> is_trusted = True (пойдёт в датасет)

    Важно:
    - Для обучения нам нужна связь “строка -> candidates -> label”.
    """

    __tablename__ = "feedback_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    session_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("feedback_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    caption: Mapped[str] = mapped_column(Text, nullable=False)

    units_in: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qty_in: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Нормализованный/распарсенный результат (опционально):
    # например: выделенные диаметры, сечения, ГОСТ, бренд, напряжение, длины и т.п.
    norm_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Доверенность: влияет на экспорт датасета
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", index=True)

    # Связи
    session = relationship("FeedbackSession", back_populates="rows")

    candidates = relationship(
        "FeedbackCandidate",
        back_populates="row",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    labels = relationship(
        "FeedbackLabel",
        back_populates="row",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    training_links = relationship(
        "TrainingRunRow",
        back_populates="row",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_feedback_rows_session_created_at", "session_id", "created_at"),
    )
