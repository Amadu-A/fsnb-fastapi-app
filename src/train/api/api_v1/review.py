# path: src/train/api/api_v1/review.py
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app_logging import get_logger
from src.core.models.db_helper import db_helper
from src.crud.item_repository import IItemRepository, ItemRepository
from src.train.models.feedback_candidate import FeedbackCandidate
from src.train.models.feedback_row import FeedbackRow
from src.train.models.feedback_session import FeedbackSession
from src.train.models.feedback_label import FeedbackLabel  # <-- добавили
from src.train.services.feedback_persist_service import FeedbackPersistService
from src.train.services.report_service import ReportService
from src.train.services.review_service import ReviewService
from src.train.utils.access import (
    get_actor_identity,
    is_actor_editor,
    require_logged_in_session,
)

router = APIRouter()
log = get_logger("train.api.review")


class ReviewCreateResponse(BaseModel):
    session_id: int
    redirect_url: str


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@router.get("/items/search")
async def items_search(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    q: str,
    limit: int = 20,
) -> JSONResponse:
    require_logged_in_session(request)

    if not q or len(q.strip()) < 2:
        return JSONResponse({"items": []})

    repo: IItemRepository = ItemRepository()
    items = await repo.search_items(session, query=q.strip(), limit=int(limit))

    payload = []
    for it in items:
        payload.append(
            {
                "id": int(it.id),
                "code": it.code,
                "name": it.name,
                "unit": it.unit,
                "type": it.type,
            }
        )

    return JSONResponse({"items": payload})


@router.post("/candidates")
async def candidates_for_rows(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    body: dict[str, Any],
) -> JSONResponse:
    require_logged_in_session(request)

    captions = body.get("captions")
    top_k = int(body.get("top_k") or 5)

    if not isinstance(captions, list) or not captions:
        raise HTTPException(status_code=400, detail="captions must be a non-empty list")

    item_repo: IItemRepository = ItemRepository()
    svc = ReviewService(item_repo=item_repo)

    result = await svc.get_topk_for_captions(
        session=session,
        captions=[str(c) for c in captions],
        top_k=top_k,
    )
    return JSONResponse({"topk": result})


@router.post("/commit")
async def commit_review_and_export_xlsx(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    body: dict[str, Any],
) -> StreamingResponse:
    """
    "Сформировать":
    1) сохраняем feedback_labels в УЖЕ созданную draft-сессию (по session_id)
    2) закрываем эту draft-сессию (status=closed)
    3) отдаём Excel (ВОР)
    """
    require_logged_in_session(request)

    actor = get_actor_identity(request)

    # is_actor_editor() делает SELECT => SQLAlchemy 2.x autobegin
    trusted = await is_actor_editor(session=session, actor_user_id=actor["user_id"])
    if session.in_transaction():
        await session.rollback()

    session_id = _safe_int(body.get("session_id"))
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    source_name = str(body.get("source_name") or "").strip() or "web_review"
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="rows must be a non-empty list")

    item_repo: IItemRepository = ItemRepository()
    review_svc = ReviewService(item_repo=item_repo)
    normalized_rows = review_svc.normalize_commit_rows(rows)

    persist_svc = FeedbackPersistService(item_repo=item_repo)
    report_svc = ReportService(item_repo=item_repo)

    try:
        async with session.begin():
            feedback_session_id = await persist_svc.persist_commit(
                session=session,
                session_id=int(session_id),  # <-- главное изменение
                source_name=source_name,
                actor_email=actor["email"],
                actor_user_id=actor["user_id"],
                is_trusted=bool(trusted),
                rows=normalized_rows,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    xlsx_bytes = await report_svc.build_result_xlsx(session=session, rows=normalized_rows)

    filename = f"VOR_{feedback_session_id}.xlsx"
    log.info(
        {
            "event": "review_committed",
            "feedback_session_id": int(feedback_session_id),
            "trusted": bool(trusted),
            "rows": len(normalized_rows),
            "filename": filename,
        }
    )

    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/create", response_model=ReviewCreateResponse)
async def review_create(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    file: UploadFile = File(...),
    top_k: int = 5,
) -> ReviewCreateResponse:
    require_logged_in_session(request)

    actor = get_actor_identity(request)
    actor_email = str(actor.get("email") or "")

    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="JSON must contain non-empty 'items' list")

    source_name = None
    if isinstance(data, dict):
        source_name = str(data.get("source_name") or data.get("source") or "").strip() or None
    if not source_name:
        source_name = file.filename or "web_review"

    captions: list[str] = [str(i.get("Caption", "") or "") for i in items]
    units_in: list[str | None] = [i.get("Units") for i in items]
    qty_in: list[str | None] = [i.get("Quantity") for i in items]

    item_repo: IItemRepository = ItemRepository()
    review_svc = ReviewService(item_repo=item_repo)

    topk = await review_svc.get_topk_for_captions(
        session=session,
        captions=captions,
        top_k=int(top_k),
    )

    if session.in_transaction():
        await session.rollback()

    async with session.begin():
        fb_session = FeedbackSession(
            source_name=source_name,
            created_by=actor_email,
            status="open",
        )
        session.add(fb_session)
        await session.flush()

        row_objs: list[FeedbackRow] = []
        for cap, u, q in zip(captions, units_in, qty_in):
            row_objs.append(
                FeedbackRow(
                    session_id=fb_session.id,
                    caption=cap,
                    units_in=u if u is not None else None,
                    qty_in=q if q is not None else None,
                    created_by=actor_email,
                    is_trusted=False,
                )
            )
        session.add_all(row_objs)
        await session.flush()

        cand_objs: list[FeedbackCandidate] = []
        for row, found in zip(row_objs, topk):
            if not found:
                continue

            for idx, cand in enumerate(found, start=1):
                if isinstance(cand, dict):
                    item_id = _safe_int(cand.get("item_id") or cand.get("id"))
                    score = cand.get("score")
                else:
                    item_id = _safe_int(getattr(cand, "id", None))
                    score = getattr(cand, "score", None)

                if item_id is None:
                    continue

                cand_objs.append(
                    FeedbackCandidate(
                        row_id=row.id,
                        item_id=item_id,
                        model_name="giga",
                        model_version=None,
                        score=float(score) if score is not None else None,
                        rank=int(idx),
                        shown=True,
                    )
                )

        if cand_objs:
            session.add_all(cand_objs)

    sid = int(fb_session.id)
    return ReviewCreateResponse(session_id=sid, redirect_url=f"/train/review/{sid}")


@router.get("/no_match/export")
async def export_no_match_rows(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    trusted_only: bool = True,
    limit: int = 1000,
    offset: int = 0,
) -> JSONResponse:
    """
    Ваши "негативы-строки" = строки спецификации, где label == none_match.
    Это именно тексты, которые "не должны матчиться ни с чем".
    """
    require_logged_in_session(request)

    actor = get_actor_identity(request)
    can_export = await is_actor_editor(session=session, actor_user_id=actor["user_id"])
    if not can_export:
        raise HTTPException(status_code=403, detail="Not allowed")

    stmt = (
        select(
            FeedbackRow.id.label("row_id"),
            FeedbackRow.session_id.label("session_id"),
            FeedbackRow.caption.label("caption"),
            FeedbackRow.units_in.label("units"),
            FeedbackRow.qty_in.label("qty"),
            FeedbackLabel.created_at.label("labeled_at"),
            FeedbackLabel.created_by.label("created_by"),
            FeedbackLabel.is_trusted.label("is_trusted"),
        )
        .select_from(FeedbackRow)
        .join(FeedbackLabel, FeedbackLabel.row_id == FeedbackRow.id)
        .where(FeedbackLabel.label == "none_match")
        .order_by(FeedbackLabel.created_at.desc())
        .limit(int(limit))
        .offset(int(offset))
    )

    if trusted_only:
        stmt = stmt.where(FeedbackLabel.is_trusted.is_(True))

    res = (await session.execute(stmt)).mappings().all()
    return JSONResponse({"items": [dict(r) for r in res]})
