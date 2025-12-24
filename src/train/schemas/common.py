# path: src/train/schemas/common.py
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMBaseSchema(BaseModel):
    """
    Базовая схема для ответов из ORM (pydantic v2).
    """
    model_config = ConfigDict(from_attributes=True)


class AlertSchema(BaseModel):
    """
    Унифицированное сообщение (если нужно для UI).
    """
    kind: str = Field(..., examples=["success", "error", "info"])
    text: str
    meta: Optional[dict[str, Any]] = None
