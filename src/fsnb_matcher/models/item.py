# src/fsnb_matcher/models/item.py
from __future__ import annotations
from sqlalchemy import Column, Integer, Text, CheckConstraint, UniqueConstraint
from src.core.models.base import Base  # общий Base

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, unique=True, index=True)       # шифр ФСНБ
    name = Column(Text, nullable=False, index=True)    # наименование
    unit = Column(Text)                                # ед.изм.
    type = Column(Text, nullable=False)                # 'work'|'resource'

    __table_args__ = (
        UniqueConstraint("code", name="uq_items_code"),
        CheckConstraint("type IN ('work','resource')", name="chk_items_type"),
    )
