# src/fsnb_matcher/api/api_v1/match.py
from __future__ import annotations
import json
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import db_helper
from src.core.config import settings
from src.fsnb_matcher.services.matcher_service import build_match_xlsx

router = APIRouter()

def _ensure_auth(request: Request) -> None:
    # тот же флаг, что в header: access_token + user_email
    if not (request.session.get("access_token") and request.session.get("user_email")):
        raise HTTPException(status_code=401, detail="Auth required")

@router.post("/match", name="fsnb_match_process")
async def fsnb_match_process(
    request: Request,
    file: UploadFile = File(...),
):
    _ensure_auth(request)

    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    try:
        xlsx = await build_match_xlsx(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="smeta.xlsx"'},
    )
