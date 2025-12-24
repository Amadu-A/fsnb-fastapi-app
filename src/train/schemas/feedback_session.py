# path: src/train/schemas/feedback_session.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from src.train.schemas.common import ORMBaseSchema


class FeedbackSessionCreate(ORMBaseSchema):
    """
    Создание/открытие сессии разметки.
    """
    source_name: Optional[str] = Field(default=None, examples=["РД_объект_А_декабрь_2025"])


class FeedbackSessionOut(ORMBaseSchema):
    """
    Ответ сессии разметки.
    """
    id: int
    source_name: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    status: str
