# path: src/train/schemas/feedback_candidate.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.train.schemas.common import ORMBaseSchema


class FeedbackCandidateOut(ORMBaseSchema):
    """
    Кандидат, показанный пользователю (один элемент top-K).
    """
    id: int
    row_id: int
    item_id: int
    model_name: str
    model_version: Optional[str] = None
    score: Optional[float] = None
    rank: Optional[int] = None
    shown: bool
    created_at: datetime
