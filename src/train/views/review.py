# path: src/train/views/review.py
from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app_logging import get_logger
from src.core.models.db_helper import db_helper
from src.crud.item_repository import IItemRepository, ItemRepository
from src.train.models.feedback_candidate import FeedbackCandidate
from src.train.models.feedback_row import FeedbackRow
from src.train.models.feedback_session import FeedbackSession
from src.train.services.review_service import ReviewService
from src.train.utils.access import require_logged_in_session

router = APIRouter()
log = get_logger("train.views.review")

PROJECT_DIR = Path(__file__).resolve().parents[2]  # /app/src
TEMPLATES_DIR = PROJECT_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# т.к. views-роутер подключаем с prefix="/train" в src/core/views/__init__.py
TRAIN_PREFIX = "/train"


def _ensure_csrf(request: Request) -> str:
    token = request.session.get("review_csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        request.session["review_csrf"] = token
    return token


@router.get("/review", name="review_upload_get")
async def review_upload_get(request: Request):
    """
    Стартовая страница: загрузка JSON спецификации.
    Ничего в БД не пишем.
    URL: /train/review
    """
    require_logged_in_session(request)
    csrf = _ensure_csrf(request)

    return templates.TemplateResponse(
        "train/review_upload.html",
        {"request": request, "csrf": csrf},
    )


@router.post("/review", name="review_upload_post")
async def review_upload_post(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    csrf_token: Annotated[str, Form(...)],
    spec_file: Annotated[UploadFile, File(...)],
    top_k: Annotated[int, Form()] = 5,
):
    """
    Принимаем JSON спецификацию, рендерим таблицу с top-K.
    Ничего в БД не пишем (JS state живёт на клиенте).
    URL: /train/review
    """
    require_logged_in_session(request)

    if csrf_token != request.session.get("review_csrf"):
        return RedirectResponse(url=f"{TRAIN_PREFIX}/review", status_code=status.HTTP_303_SEE_OTHER)

    content = await spec_file.read()
    try:
        payload = json.loads(content.decode("utf-8", errors="ignore"))
    except Exception:
        return templates.TemplateResponse(
            "train/review_upload.html",
            {
                "request": request,
                "csrf": _ensure_csrf(request),
                "alert": {"kind": "error", "text": "Не удалось прочитать JSON."},
            },
            status_code=400,
        )

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return templates.TemplateResponse(
            "train/review_upload.html",
            {
                "request": request,
                "csrf": _ensure_csrf(request),
                "alert": {"kind": "error", "text": "В JSON нет массива items."},
            },
            status_code=400,
        )

    # caption/units/qty берём “как есть” (без нормализации)
    rows: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        rows.append(
            {
                "caption": str(it.get("Caption", "") or ""),
                "units": str(it.get("Units", "") or "") or None,
                "qty": str(it.get("Quantity", "") or "") or None,
            }
        )

    item_repo: IItemRepository = ItemRepository()
    svc = ReviewService(item_repo=item_repo)

    view_rows = await svc.build_initial_view_rows(
        session=session,
        rows=rows,
        top_k=int(top_k),
    )

    csrf = _ensure_csrf(request)

    log.info({"event": "review_rendered_upload", "rows": len(view_rows), "top_k": int(top_k)})

    return templates.TemplateResponse(
        "train/review_table.html",
        {
            "request": request,
            "csrf": csrf,
            "source_name": spec_file.filename or "web_upload",
            "rows": view_rows,
            "top_k": int(top_k),
        },
    )


@router.get("/review/{session_id}", name="review_table_get")
async def review_table_get(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    session_id: int,
):
    """
    Страница ревью по сохранённой draft-сессии из БД.
    URL: /train/review/<id>
    """
    require_logged_in_session(request)
    csrf = _ensure_csrf(request)

    stmt = (
        select(FeedbackSession)
        .where(FeedbackSession.id == session_id)
        .options(
            selectinload(FeedbackSession.rows).selectinload(FeedbackRow.candidates),
        )
    )
    res = await session.execute(stmt)
    fb_session = res.scalar_one_or_none()

    if fb_session is None:
        return templates.TemplateResponse(
            "train/review_upload.html",
            {
                "request": request,
                "csrf": csrf,
                "alert": {"kind": "error", "text": f"Сессия {session_id} не найдена."},
            },
            status_code=404,
        )

    # соберём item_id кандидатов -> подтянем мету батчем (name/unit/code)
    item_ids: set[int] = set()
    for row in fb_session.rows or []:
        for cand in row.candidates or []:
            if cand.item_id is not None:
                item_ids.add(int(cand.item_id))

    item_repo: IItemRepository = ItemRepository()
    meta = {}
    if item_ids:
        # meta[item_id] = (name, unit, code)
        meta = await item_repo.fetch_items_meta_by_ids(session=session, item_ids=sorted(item_ids))

    # приводим строки к формату, который ожидает шаблон review_table.html
    view_rows: list[dict[str, Any]] = []

    for idx, r in enumerate(fb_session.rows or []):
        cands_sorted = sorted(r.candidates or [], key=lambda x: (x.rank or 10**9))

        candidates: list[dict[str, Any]] = []
        for c in cands_sorted:
            item_id = int(c.item_id)
            name, unit, code = meta.get(item_id, (None, None, None))

            candidates.append(
                {
                    "id": item_id,
                    "code": code,
                    "name": name,
                    "unit": unit,
                    "score": float(c.score) if c.score is not None else None,
                }
            )

        auto_id = candidates[0]["id"] if candidates else None
        auto_label = "gold" if auto_id is not None else "none_match"

        view_rows.append(
            {
                "row_idx": int(idx),
                "caption": r.caption or "",
                "units": r.units_in,
                "qty": r.qty_in,
                "candidates": candidates,
                "auto_selected_item_id": auto_id,
                "selected_item_id": auto_id,  # дефолт: auto = top1
                "label": auto_label,
                "note": "",
            }
        )

    log.info(
        {
            "event": "review_rendered_db",
            "session_id": int(session_id),
            "rows": len(view_rows),
        }
    )

    return templates.TemplateResponse(
        "train/review_table.html",
        {
            "request": request,
            "csrf": csrf,
            "source_name": fb_session.source_name or "web_review",
            "rows": view_rows,
            "top_k": 5,
            "session_id": int(fb_session.id),
        },
    )
