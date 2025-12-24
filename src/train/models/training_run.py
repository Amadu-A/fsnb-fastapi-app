# path: src/train/models/training_run.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from sqlalchemy import BigInteger, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.models.base import Base


class TrainingRun(Base):
    """
    Таблица training_runs — реестр запусков обучения.

    Зачем нужна:
    - заменяет “trained boolean”: вместо флага мы фиксируем конкретный запуск обучения;
    - позволяет воспроизводить обучение:
        * mode (biencoder/cross/query_adapter)
        * base_model
        * data_spec (фильтры/параметры экспорта)
        * artifacts_path
        * metrics
        * статус/логи

    Типичный flow:
    - пользователь разметил -> накопились trusted метки
    - запускаем train -> создаём training_run (status=running)
    - экспортируем данные -> обучаем -> пишем metrics -> status=ok/failed
    - связываем какие строки были использованы (training_run_rows)
    """

    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    mode: Mapped[str] = mapped_column(Text, nullable=False)       # 'cross'|'query_adapter'|'biencoder'
    base_model: Mapped[str] = mapped_column(Text, nullable=False) # идентификатор базовой модели

    data_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # фильтры, max_rows и т.д.

    artifacts_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")  # running|ok|failed
    log_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Связи
    rows = relationship(
        "TrainingRunRow",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_training_runs_status", "status"),
        Index("ix_training_runs_mode_started_at", "mode", "started_at"),
    )
