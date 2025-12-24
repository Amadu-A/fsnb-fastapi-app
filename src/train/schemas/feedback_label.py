# path: src/train/schemas/feedback_label.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from src.train.models.enums import FeedbackLabel
from src.train.schemas.common import ORMBaseSchema


class FeedbackLabelCreate(ORMBaseSchema):
    """
    Сохранение метки пользователем.

    Правила (проверим в API/сервисах):
    - label=gold -> selected_item_id обязателен
    - label=negative -> negatives желательно не пустой (или хотя бы есть “ошибка top1”)
    """
    row_id: int
    label: FeedbackLabel = Field(..., examples=[FeedbackLabel.GOLD])
    selected_item_id: Optional[int] = Field(default=None, examples=[202])
    negatives: List[int] = Field(default_factory=list, examples=[[101, 303]])
    note: Optional[str] = Field(default=None, examples=["ключ: 3×2.5 и труба"])


class FeedbackLabelOut(ORMBaseSchema):
    """
    Ответ по метке.
    """
    id: int
    row_id: int
    label: str
    selected_item_id: Optional[int] = None
    negatives: List[int]
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    is_trusted: bool
