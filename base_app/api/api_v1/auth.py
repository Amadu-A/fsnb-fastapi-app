# /base_app/api/api_v1/auth.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.models import db_helper
from base_app.core.models.user import User
from base_app.core.models.profile import Profile
from base_app.core.logging import get_logger
from base_app.core.email_tokens import read_email_token
from base_app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])
log = get_logger("api.auth")


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def auth_register(
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    password2: Annotated[str, Form(...)],
):
    if password != password2:
        return {"ok": False, "detail": "Passwords do not match"}

    service = AuthService()
    user_id, verify_token = await service.register_user(session, email=email, password=password)
    await session.commit()
    log.info({"event": "register", "user_id": user_id, "email": email})
    return {"ok": True, "user_id": user_id, "verify_token": verify_token}


@router.post("/token")
async def auth_token(
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    service = AuthService()
    token = await service.authenticate(session, email=form.username, password=form.password)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/verify", response_class=HTMLResponse)
async def verify_email(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    token: str,
):
    """
    Проверка e-mail по токену: включает Profile.verification = True.
    """
    try:
        data = read_email_token(token)
        uid = int(data["uid"])
    except Exception:
        return HTMLResponse("<h3>Неверная или истёкшая ссылка подтверждения</h3>", status_code=400)

    # отмечаем профиль как верифицированный
    res = await session.execute(select(Profile).join(User).where(User.id == uid))
    profile = res.scalar_one_or_none()
    if not profile:
        return HTMLResponse("<h3>Профиль не найден</h3>", status_code=404)

    profile.verification = True
    await session.commit()
    return HTMLResponse("<h3>Почта подтверждена. Спасибо!</h3>")
