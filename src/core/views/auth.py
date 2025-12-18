# /src/core/views/auth.py
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.core.models import db_helper
from src.app_logging import get_logger
from src.core.mailing.email import send_verification_email_sync
from src.core.services.auth_service import AuthService
from src.crud.user_repository import UserRepository  # <-- добавили

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


# ---------- LOGIN (GET) ----------
@router.get("/auth/login", name="login_html")
async def login_html(request: Request):
    csrf = _ensure_csrf(request)
    a, b, _ = _new_captcha(request)
    log.info({"event": "open_page", "path": "/auth/login", "method": "GET"})
    return templates.TemplateResponse(
        "core/login.html",
        {"request": request, "csrf": csrf, "a": a, "b": b},
    )


# ---------- LOGIN (POST) ----------
@router.post("/auth/login", name="login_post_html")
async def login_post_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    email: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
    captcha: Annotated[int, Form(...)],
):
    # CSRF
    if csrf_token != request.session.get("csrf"):
        log.info({"event": "login_fail", "reason": "csrf"})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/login.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": "CSRF error"}},
            status_code=400,
        )

    # Капча
    try:
        if int(captcha) != int(request.session.get("captcha_sum", -1)):
            raise ValueError
    except Exception:
        log.info({"event": "login_fail", "reason": "bad_captcha"})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/login.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": "Капча неверна"}},
            status_code=400,
        )

    service = AuthService()
    repo = UserRepository()
    email_norm = email.strip().lower()

    try:
        # Проверяем логин/пароль (важно только отсутствие исключения)
        await service.authenticate(session, email=email_norm, password=password)

        # Берём модель пользователя
        user = await repo.get_by_email(session, email=email_norm)
        if not user:
            raise ValueError("user_not_found_after_auth")

        # КРИТИЧНО: НЕ лезем в user.profile напрямую (lazyload)!
        # Явно читаем профиль отдельным запросом:
        profile = await repo.get_profile_by_user_id(session, user_id=user.id)
        email_verified = bool(getattr(profile, "verification", False))

    except ValueError:
        log.info({"event": "login_fail", "reason": "bad_credentials_or_not_found", "email": email_norm})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/login.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": "Неверный e-mail или пароль"}},
            status_code=400,
        )

    # Успех — кладём токен в сессию и редиректим на главную
    access_token = service.make_access_token(
        email=user.email,
        uid=user.id,
        email_verified=email_verified,
    )
    request.session["access_token"] = access_token
    request.session["user_email"] = user.email
    request.session["user_id"] = user.id

    log.info({"event": "login_ok", "email": user.email, "email_verified": email_verified})
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# ---------- REGISTER (GET) ----------
@router.get("/auth/register", name="register_html")
async def register_html(request: Request):
    csrf = _ensure_csrf(request)
    a, b, _ = _new_captcha(request)
    log.info({"event": "open_page", "path": "/auth/register", "method": "GET"})
    return templates.TemplateResponse(
        "core/register.html",
        {"request": request, "csrf": csrf, "a": a, "b": b},
    )


# ---------- REGISTER (POST) ----------
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
        log.info({"event": "register_fail", "email": email, "reason": "csrf"})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": "CSRF error"}},
            status_code=400,
        )

    # Капча
    try:
        if int(captcha) != int(request.session.get("captcha_sum", -1)):
            raise ValueError
    except Exception:
        log.info({"event": "register_fail", "email": email, "reason": "bad_captcha"})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": "Капча неверна"}},
            status_code=400,
        )

    # Пароль
    email_norm = email.strip().lower()
    if len(password) < 8 or len(password) > 256 or password != password2:
        log.info({"event": "register_fail", "email": email_norm, "reason": "weak_or_mismatch_password"})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": "Пароль должен быть 8..256 символов и совпадать."}},
            status_code=400,
        )

    service = AuthService()
    try:
        user_id, verify_token = await service.register_user(session, email=email_norm, password=password)
        await session.commit()

        # ссылка подтверждения
        verify_link = str(request.url_for("verify_email", token=verify_token))
        log.info({"event": "verify_link", "email": email_norm, "verify_link": verify_link})

        # письмо в фоне
        background.add_task(send_verification_email_sync, email_norm, verify_link)

        # авто-логин
        access_token = service.make_access_token(email=email_norm, uid=user_id, email_verified=False)
        request.session["access_token"] = access_token
        request.session["user_email"] = email_norm
        request.session["user_id"] = user_id

        log.info({"event": "register_success", "email": email_norm, "user_id": user_id})
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    except ValueError as e:
        # pre-check
        if str(e) == "email_already_exists":
            log.info({"event": "register_fail", "email": email_norm, "reason": "precheck_exists"})
            csrf = _ensure_csrf(request)
            a, b, _ = _new_captcha(request)
            return templates.TemplateResponse(
                "core/register.html",
                {"request": request, "csrf": csrf, "a": a, "b": b,
                 "alert": {"kind": "error", "text": "Пользователь с таким e-mail уже существует"}},
                status_code=400,
            )
        await session.rollback()
        log.info({"event": "register_fail", "email": email_norm, "error": str(e)})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": f"Ошибка регистрации: {e}"}},
            status_code=400,
        )
    except IntegrityError as e:
        await session.rollback()
        cname = getattr(getattr(e, "orig", None), "constraint_name", None)
        txt = str(getattr(e, "orig", e))
        human = "Нарушение целостности данных."
        if "not-null constraint" in txt or "NotNullViolation" in txt:
            human = "Внутренняя ошибка схемы: одно из полей пустое. Обнови миграции (username теперь необязателен)."
        elif cname == "uq_users_email" or "uq_users_email" in txt:
            human = "Пользователь с таким e-mail уже зарегистрирован"
        elif cname == "uq_users_username" or "uq_users_username" in txt:
            human = "Такой username уже занят"
        log.info({"event": "register_fail", "email": email_norm, "constraint": cname, "sql_error": txt})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": human}},
            status_code=400,
        )
    except Exception as e:
        await session.rollback()
        log.info({"event": "register_fail", "email": email_norm, "error": str(e)})
        csrf = _ensure_csrf(request)
        a, b, _ = _new_captcha(request)
        return templates.TemplateResponse(
            "core/register.html",
            {"request": request, "csrf": csrf, "a": a, "b": b,
             "alert": {"kind": "error", "text": "Не удалось зарегистрировать пользователя"}},
            status_code=400,
        )


# ---------- VERIFY EMAIL ----------
@router.get("/auth/verify/{token}", name="verify_email")
async def verify_email(
    request: Request,
    token: str,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    service = AuthService()
    try:
        uid = await service.verify_email(session, token)
        await session.commit()

        # если тот же пользователь в сессии — перезальём токен с флагом
        if request.session.get("user_id") == uid:
            access_token = service.make_access_token(
                email=request.session.get("user_email", ""),
                uid=uid,
                email_verified=True,
            )
            request.session["access_token"] = access_token

        log.info({"event": "verify_ok", "uid": uid})
        alert = {"kind": "success", "text": "E-mail подтвержден. Спасибо!"}
    except Exception as e:
        await session.rollback()
        log.info({"event": "verify_fail", "error": str(e)})
        alert = {"kind": "error", "text": "Ссылка недействительна или устарела."}

    return templates.TemplateResponse("core/index.html", {"request": request, "alert": alert})


# ---------- LOGOUT ----------
@router.post("/auth/logout", name="logout_html")
@router.get("/auth/logout")
async def logout_html(request: Request):
    request.session.pop("access_token", None)
    request.session.pop("user_email", None)
    request.session.pop("user_id", None)
    log.info({"event": "logout_ok"})
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
