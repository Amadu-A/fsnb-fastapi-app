# /src/core/api/api_v1/auth.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.models import db_helper
from src.logging import get_logger
from src.core.services.auth_service import AuthService

router = APIRouter(prefix=settings.api.v1.auth, tags=["auth"])
log = get_logger("api.auth")


@router.post("/token")
async def auth_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    """
    Точка входа OAuth2 Password:
    - Принимает form.username (email) и form.password (x-www-form-urlencoded)
    - Возвращает {"access_token": "...", "token_type": "bearer"}
    """
    service = AuthService()
    try:
        token = await service.authenticate(session, email=form.username.strip().lower(), password=form.password)
        return {"access_token": token, "token_type": "bearer"}
    except ValueError:
        # 401 — неправильные креды
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    except Exception as e:
        log.info({"event": "auth_token_fail", "error": str(e)})
        raise HTTPException(status_code=500, detail="Auth failed")
