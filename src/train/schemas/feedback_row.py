# path: src/train/schemas/feedback_row.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, List

from pydantic import Field

from src.train.schemas.common import ORMBaseSchema


class FeedbackRowIn(ORMBaseSchema):
    """
    Одна строка спецификации на вход в /review/rows.
    """
    caption: str = Field(..., min_length=1, examples=["Кабель ВВГнг(А)-LS 3×2.5"])
    units_in: Optional[str] = Field(default=None, examples=["м"])
    qty_in: Optional[str] = Field(default=None, examples=["120"])
    norm_json: Optional[dict[str, Any]] = Field(
        default=None,
        description="Опциональный результат нормализации/парсинга (позже подключим).",
        examples=[{"parsed": {"section": "3x2.5", "gost": "ГОСТ ..."}}],
    )


class FeedbackRowsCreate(ORMBaseSchema):
    """
    Батч создание строк в рамках feedback_session.
    """
    session_id: int
    rows: List[FeedbackRowIn]


class FeedbackRowOut(ORMBaseSchema):
    """
    Ответ по строке.
    """
    id: int
    session_id: Optional[int] = None
    caption: str
    units_in: Optional[str] = None
    qty_in: Optional[str] = None
    norm_json: Optional[dict[str, Any]] = None
    created_by: Optional[str] = None
    created_at: datetime
    is_trusted: bool
