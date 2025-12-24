# path: src/train/models/feedback_label.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.models.base import Base
from src.train.models.enums import FeedbackLabel as FeedbackLabelEnum


class FeedbackLabel(Base):
    """
    Таблица feedback_labels — “решение пользователя” по строке.

    Зачем нужна:
    - хранит фактическую разметку (gold/negative/skip/ambiguous/none_match)
    - хранит selected_item_id для gold (истина)
    - хранит negatives (список items.id, которые пользователь считает неверными)
    - хранит is_trusted:
        * is_reader -> False (draft)
        * editor    -> True  (идёт в датасет)

    Важно:
    - Мы допускаем историю правок (несколько записей на одну row_id).
      Экспорт датасета обычно берёт “последнюю trusted” метку (эту логику сделаем в SQL VIEW/экспорте).
    """

    __tablename__ = "feedback_labels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    row_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feedback_rows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Метка
    label: Mapped[str] = mapped_column(
        Text,  # оставляем Text, чтобы миграции были проще; enum-тип можно добавить позже
        nullable=False,
    )

    # Выбранный items.id (обязателен для gold; проверим в приложении/валидации)
    selected_item_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Негативы: список items.id, которые неверны для данной строки
    negatives: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, server_default="{}")

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", index=True)

    # Связи
    row = relationship("FeedbackRow", back_populates="labels")

    __table_args__ = (
        Index("ix_feedback_labels_row_created_at", "row_id", "created_at"),
        Index("ix_feedback_labels_label", "label"),
    )

    @staticmethod
    def normalize_label(value: str) -> str:
        """
        Нормализатор метки на случай, если форма пришлёт "GOLD"/"Gold" и т.п.
        """
        v = (value or "").strip().lower()
        allowed = {e.value for e in FeedbackLabelEnum}
        return v if v in allowed else FeedbackLabelEnum.SKIP.value
