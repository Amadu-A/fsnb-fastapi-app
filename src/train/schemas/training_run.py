# path: src/train/schemas/training_run.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from src.train.schemas.common import ORMBaseSchema


class TrainingRunCreate(ORMBaseSchema):
    """
    Создание запуска обучения (обычно делает воркер/таск, но API тоже может).
    """
    mode: str = Field(..., examples=["biencoder"])
    base_model: str = Field(..., examples=["Giga-Embeddings-instruct"])
    data_spec: dict[str, Any] = Field(
        default_factory=dict,
        description="Фильтры и параметры выгрузки/обучения (дат, источники, max_rows и т.п.)",
        examples=[{"from": "2025-12-01", "to": "2025-12-22", "only_trusted": True, "max_rows": 5000}],
    )
    created_by: Optional[str] = None


class TrainingRunOut(ORMBaseSchema):
    """
    Ответ по запуску обучения.
    """
    id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    mode: str
    base_model: str
    data_spec: dict[str, Any]
    artifacts_path: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None
    status: str
    log_path: Optional[str] = None
    created_by: Optional[str] = None
