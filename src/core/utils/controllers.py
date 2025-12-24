# path: src/core/utils/controllers.py
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin import admin_site
from src.core.utils import (
    build_pagination,
    coerce_value,
    get_boolean_fields,
    get_columns,
    get_fk_target_table,
    parse_bool,
)

PAGE_SIZE = 50


def build_base_query_params(request: Request) -> dict[str, str]:
    # все query params, кроме page
    qp: dict[str, str] = {}
    for k, v in request.query_params.items():
        if k == "page":
            continue
        qp[k] = v
    return qp


def make_url(request: Request, *, page: int, base_params: dict[str, str]) -> str:
    # сохраним все фильтры/поиск и добавим page
    from urllib.parse import urlencode

    params = dict(base_params)
    params["page"] = str(page)
    return str(request.url.replace(query=urlencode(params, doseq=True)))


async def admin_model_list_view(
    request: Request,
    session: AsyncSession,
    slug: str,
) -> dict[str, Any]:
    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")

    model = ma.model
    cols = get_columns(model)

    # page
    try:
        page = int(request.query_params.get("page", "1"))
    except Exception:
        page = 1

    page_size = ma.page_size or PAGE_SIZE

    # search
    q = (request.query_params.get("q") or "").strip()

    stmt = select(model)
    count_stmt = select(func.count()).select_from(model)

    # exact filters: любой query param, совпадающий с колонкой -> equality
    # + булевы: "true/false/1/0"
    for key, raw in request.query_params.items():
        if key in {"page", "q"}:
            continue
        if key not in cols:
            continue
        if raw is None or str(raw).strip() == "":
            continue
        val = coerce_value(cols[key], raw)
        if val is None:
            continue
        stmt = stmt.where(getattr(model, key) == val)
        count_stmt = count_stmt.where(getattr(model, key) == val)

    # LIKE search по search_fields
    if q and ma.search_fields:
        like_parts = []
        for f in ma.search_fields:
            if f in cols:
                like_parts.append(getattr(model, f).ilike(f"%{q}%"))
        if like_parts:
            stmt = stmt.where(or_(*like_parts))
            count_stmt = count_stmt.where(or_(*like_parts))

    total = (await session.execute(count_stmt)).scalar_one()
    pagination = build_pagination(total=total, page=page, page_size=page_size)

    # ordering: если есть created_at -> desc, иначе по pk/первой колонке
    if "created_at" in cols:
        stmt = stmt.order_by(getattr(model, "created_at").desc())
    elif "id" in cols:
        stmt = stmt.order_by(getattr(model, "id").desc())

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    rows = (await session.execute(stmt)).scalars().all()

    # bool filter UI (для train нужно, но можно показывать всегда)
    bool_fields = get_boolean_fields(model)

    # fk links map: field -> target_slug + target_field="id"
    fk_map: dict[str, dict[str, str]] = {}
    for name, col in cols.items():
        target_table = get_fk_target_table(col)
        if not target_table:
            continue
        # slug обычно == table name
        if admin_site.get(target_table):
            fk_map[name] = {"slug": target_table, "field": "id"}

    base_params = build_base_query_params(request)
    prev_url = make_url(request, page=pagination.prev_page, base_params=base_params) if pagination.has_prev else None
    next_url = make_url(request, page=pagination.next_page, base_params=base_params) if pagination.has_next else None

    return {
        "model_name": model.__name__,
        "slug": slug,
        "ma": ma,
        "rows": rows,
        "list_display": ma.list_display,
        "q": q,
        "bool_fields": bool_fields,
        "fk_map": fk_map,
        "pagination": pagination,
        "prev_url": prev_url,
        "next_url": next_url,
        "base_params": base_params,  # для сборки ссылок в шаблоне при необходимости
    }


async def admin_model_clear_all(session: AsyncSession, slug: str) -> None:
    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")
    if not ma.can_delete:
        raise HTTPException(status_code=403, detail="Clear not allowed")
    await session.execute(delete(ma.model))
    await session.commit()
