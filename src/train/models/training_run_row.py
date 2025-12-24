# path: src/train/models/training_run_row.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.models.base import Base


class TrainingRunRow(Base):
    """
    Таблица training_run_rows — связка “какие feedback_rows ушли в какой training_run”.

    Зачем нужна:
    - обеспечивает неизменяемую историю: какие именно строки были в конкретном обучении;
    - позволяет “не мешаться” с новыми данными:
        * при экспорте можно исключать уже использованные строки для конкретного mode/запуска
        * можно считать покрытие и эффективность обучения по партиям
    """

    __tablename__ = "training_run_rows"

    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("training_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )

    row_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("feedback_rows.id", ondelete="CASCADE"),
        primary_key=True,
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Связи
    run = relationship("TrainingRun", back_populates="rows")
    row = relationship("FeedbackRow", back_populates="training_links")

    __table_args__ = (
        Index("ix_training_run_rows_row_id", "row_id"),
        Index("ix_training_run_rows_run_id", "run_id"),
    )
