# path: src/train/models/feedback_candidate.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.models.base import Base


class FeedbackCandidate(Base):
    """
    Таблица feedback_candidates — “что именно показывали пользователю”.

    Зачем нужна (критично):
    - обучение и штрафы требуют контекста top-K:
        * какие candidates были доступны при выборе;
        * какие scores/ranks показала модель;
        * какие negatives указал пользователь.
    - без кандидатов в обучении пропадает важная информация:
        * hard negatives (высокий скор, но неверно)
        * анализ качества по rank/score

    Поля:
    - row_id: к какой входной строке относится candidate
    - item_id: ссылка на items.id
    - model_name/model_version: кто именно предсказал (важно при A/B и смене прод-версии)
    - score/rank: показатели ранжирования
    - shown: можно хранить “показывали ли” (если вдруг фильтруем часть кандидатов)
    """

    __tablename__ = "feedback_candidates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    row_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feedback_rows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    shown: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Связи
    row = relationship("FeedbackRow", back_populates="candidates")

    __table_args__ = (
        UniqueConstraint("row_id", "item_id", "model_name", name="uq_feedback_candidates_row_item_model"),
        Index("ix_feedback_candidates_row_rank", "row_id", "rank"),
    )
