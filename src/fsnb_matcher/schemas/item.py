# src/fsnb_matcher/schemas/item.py
from __future__ import annotations
from pydantic import BaseModel

class ItemMeta(BaseModel):
    id: int
    code: str | None
    name: str
    unit: str | None
    type: str
