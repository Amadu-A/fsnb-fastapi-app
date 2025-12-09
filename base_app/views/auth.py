# /base_app/views/auth.py
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError  # <- чтобы ловить UNIQUE-ошибки

from base_app.core.models import db_helper
from base_app.core.logging import get_logger
from base_app.mailing.email import send_verification_email_sync
from base_app.services.auth_service import AuthService

router = APIRouter()
log = get_logger("views.auth")

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        request.session["csrf"] = token
    return token


def _new_captcha(request: Request) -> tuple[int, int, int]:
    a = secrets.randbelow(9) + 1
    b = secrets.randbelow(9) + 1
    s = a + b
    request.session["captcha_sum"] = s
    return a, b, s


@router.get("/auth/login", name="login_html")
async def login_html(request: Request):
    csrf = _ensure_csrf(request)
    a, b, _ = _new_captcha(request)
    return templates.TemplateResponse("core/login.html", {"request": request, "csrf": csrf, "a": a, "b": b})


@router.get("/auth/register", name="register_html")
async def register_html(request: Request):
    csrf = _ensure_csrf(request)
    a, b, _ = _new_captcha(request)
    return templates.TemplateResponse("core/register.html", {"request": request, "csrf": csrf, "a": a, "b": b})


@router.post("/auth/register", name="register_post_html")
async def register_post_html(
    request: Request,
    background: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    password2: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
    captcha: Annotated[int, Form(...)],
):
    # CSRF
    if csrf_token != request.session.get("csrf"):
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request), "alert": {"kind": "error", "text": "CSRF error"}},
            status_code=400,
        )
    # CAPTCHA
    try:
        if int(captcha) != int(request.session.get("captcha_sum", -1)):
            raise ValueError
    except Exception:
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request), "alert": {"kind": "error", "text": "Капча неверна"}},
            status_code=400,
        )

    # Нормализация и валидация полей
    email = email.strip().lower()
    if len(password) < 8 or len(password2) < 8:
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request),
             "alert": {"kind": "error", "text": "Пароль должен быть не короче 8 символов"}},
            status_code=400,
        )
    if len(password) > 256 or len(password2) > 256:
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request),
             "alert": {"kind": "error", "text": "Пароль слишком длинный (макс. 256 символов)"}},
            status_code=400,
        )
    if password != password2:
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request),
             "alert": {"kind": "error", "text": "Пароли не совпадают"}},
            status_code=400,
        )

    service = AuthService()
    try:
        user_id, verify_token = await service.register_user(session, email=email, password=password)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        log.info({"event": "register_fail", "email": email, "error": "email already exists"})
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request),
             "alert": {"kind": "error", "text": "Пользователь с таким e-mail уже зарегистрирован"}},
            status_code=400,
        )
    except ValueError as e:
        # На случай, если где-то в стеке ещё встретится ограничение bcrypt.
        await session.rollback()
        log.info({"event": "register_fail", "email": email, "error": str(e)})
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request),
             "alert": {"kind": "error", "text": f"Ошибка пароля: {e}"}},
            status_code=400,
        )
    except Exception as e:
        await session.rollback()
        log.info({"event": "register_fail", "email": email, "error": str(e)})
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": _ensure_csrf(request),
             "alert": {"kind": "error", "text": "Не удалось зарегистрировать пользователя"}},
            status_code=400,
        )

    verify_link = str(request.url_for("verify_email", token=verify_token))
    background.add_task(send_verification_email_sync, email, verify_link)

    success_alert = {
        "kind": "success",
        "text": "Мы отправили письмо с подтверждением. Перейдите по ссылке из письма, чтобы завершить регистрацию.",
    }
    return templates.TemplateResponse("core/index.html", {"request": request, "alert": success_alert})
