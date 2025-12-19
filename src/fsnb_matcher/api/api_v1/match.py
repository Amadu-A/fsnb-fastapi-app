# path: src/fsnb_matcher/api/api_v1/match.py
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.db_helper import db_helper
from src.crud.item_repository import IItemRepository
from src.fsnb_matcher.api.api_v1.deps import get_item_repository
from src.fsnb_matcher.services.matcher_service import build_match_xlsx


router = APIRouter()


def _ensure_auth(request: Request) -> None:
    """
    Проверяем, что пользователь залогинен.

    Логика как была: используем session middleware, где кладутся access_token и user_email.
    """
    if not (request.session.get("access_token") and request.session.get("user_email")):
        raise HTTPException(status_code=401, detail="Auth required")


@router.post("/match", name="fsnb_match_process")
async def fsnb_match_process(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_helper.session_getter),
    item_repo: IItemRepository = Depends(get_item_repository),
) -> Response:
    """
    Принимаем JSON-файл и возвращаем xlsx.

    DI-правило:
    - session даёт db_helper через Depends
    - item_repo даёт get_item_repository (интерфейс + реализация в crud)
    - build_match_xlsx вызываем с session и repo
    """
    _ensure_auth(request)

    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    try:
        xlsx = await build_match_xlsx(session, item_repo, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="smeta.xlsx"'},
    )
