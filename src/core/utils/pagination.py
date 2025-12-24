# path: src/core/utils/pagination.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, Integer
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.sql.schema import Column


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int
    total: int
    pages: int
    has_prev: bool
    has_next: bool
    prev_page: int
    next_page: int
    offset: int
    limit: int


def build_pagination(*, total: int, page: int, page_size: int) -> Pagination:
    if page_size <= 0:
        page_size = 50
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    offset = (page - 1) * page_size
    return Pagination(
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
        has_prev=page > 1,
        has_next=page < pages,
        prev_page=max(1, page - 1),
        next_page=min(pages, page + 1),
        offset=offset,
        limit=page_size,
    )


def get_columns(model: type[DeclarativeMeta]) -> dict[str, Column]:
    return {c.name: c for c in model.__table__.columns}


def get_boolean_fields(model: type[DeclarativeMeta]) -> list[str]:
    cols = get_columns(model)
    out: list[str] = []
    for name, col in cols.items():
        try:
            if isinstance(col.type, Boolean):
                out.append(name)
        except Exception:
            continue
    return out


def parse_bool(v: str | None) -> Optional[bool]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return None


def coerce_value(col: Column, raw: str | None) -> Any:
    if raw is None:
        return None
    if isinstance(col.type, Boolean):
        return parse_bool(raw)
    if isinstance(col.type, (Integer, BigInteger)):
        try:
            return int(raw)
        except Exception:
            return None
    return raw


def get_fk_target_table(col: Column) -> Optional[str]:
    fks = list(col.foreign_keys)
    if not fks:
        return None
    fk = fks[0]
    if fk.column is None:
        return None
    return fk.column.table.name
