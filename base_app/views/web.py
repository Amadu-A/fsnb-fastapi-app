# /base_app/views/web.py
from __future__ import annotations

import os
import io
from datetime import datetime
from PIL import Image
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.logging import get_logger
from base_app.core.models import db_helper
from base_app.crud.user_repository import UserRepository, get_all_users

router = APIRouter()
log = get_logger("web")

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
AVATAR_DIR = STATIC_DIR / "uploads" / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)

# --- Ограничения на аватар ---
MAX_AVATAR_MB = 3
MAX_AVATAR_BYTES = MAX_AVATAR_MB * 1024 * 1024
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


@router.get("/", name="home")
async def index_html(request: Request):
    """
    Главная страница.
    Имя роута — 'home' (используется в templates/core/_header.html).
    """
    log.info({"event": "open_page", "path": "/", "method": "GET"})
    return templates.TemplateResponse("core/index.html", {"request": request})


@router.get("/users/", name="users_list_html")
async def users_list_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    """HTML-страница со списком пользователей."""
    users = await get_all_users(session)
    log.info({"event": "open_page", "path": "/users/", "method": "GET", "count": len(users)})
    return templates.TemplateResponse("users/list.html", {"request": request, "users": users})


def _require_logged_in(request: Request) -> Optional[str]:
    """Возвращает email пользователя из сессии, если он залогинен, иначе None."""
    token = request.session.get("access_token")
    email = request.session.get("user_email")
    if not token or not email:
        return None
    return email


@router.get("/profile", name="profile_html")
async def profile_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    """Профиль пользователя (форма редактирования)."""
    email = _require_logged_in(request)
    if not email:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    repo = UserRepository()
    user = await repo.get_by_email(session, email=email)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    profile = await repo.get_profile_by_user_id(session, user_id=user.id)
    return templates.TemplateResponse("core/profile.html", {"request": request, "user": user, "profile": profile})


@router.post("/profile", name="profile_post_html")
async def profile_post_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    nickname: Annotated[str | None, Form()] = None,
    first_name: Annotated[str | None, Form()] = None,
    second_name: Annotated[str | None, Form()] = None,
    phone: Annotated[str | None, Form()] = None,
    email_field: Annotated[str | None, Form()] = None,  # поле email профиля (не user.email)
    tg_id: Annotated[str | None, Form()] = None,
    tg_nickname: Annotated[str | None, Form()] = None,
    session_str: Annotated[str | None, Form()] = None,
    avatar: Annotated[UploadFile | None, File()] = None,
):
    """Обработка формы профиля. Валидация аватара: тип=image/*, размер ≤ 3 МБ. Перезапись старого файла."""
    def _clean_str(v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s if s else None

    def _clean_tg_id(v: str | None) -> int | None:
        if not v:
            return None
        s = v.strip()
        if not s:
            return None
        digits = "".join(ch for ch in s if ch.isdigit())
        return int(digits) if digits else None

    email = _require_logged_in(request)
    if not email:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    repo = UserRepository()
    user = await repo.get_by_email(session, email=email)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    profile = await repo.get_profile_by_user_id(session, user_id=user.id)
    if not profile:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    updates: dict[str, object] = {
        "nickname": _clean_str(nickname),
        "first_name": _clean_str(first_name),
        "second_name": _clean_str(second_name),
        "phone": _clean_str(phone),
        "email": _clean_str(email_field),
        "tg_id": _clean_tg_id(tg_id),
        "tg_nickname": _clean_str(tg_nickname),
        "session": _clean_str(session_str),
    }

    # загрузка аватара
    if avatar and avatar.filename:
        # 1) Контент-тайп
        allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if avatar.content_type not in allowed:
            alert = {"kind": "error", "text": "Только изображения (JPG/PNG/GIF/WebP)."}
            return templates.TemplateResponse("core/profile.html",
                                              {"request": request, "user": user, "profile": profile, "alert": alert})

        # 2) Размер
        content = await avatar.read()
        MAX_BYTES = 3 * 1024 * 1024
        if len(content) > MAX_BYTES:
            alert = {"kind": "error", "text": "Файл слишком большой. Максимум 3 МБ."}
            return templates.TemplateResponse("core/profile.html",
                                              {"request": request, "user": user, "profile": profile, "alert": alert})

        # 3) Геометрия (минимум 40x40)
        try:
            im = Image.open(io.BytesIO(content))
            im.load()
            if im.width < 40 or im.height < 40:
                alert = {"kind": "error", "text": "Минимальный размер изображения — 40×40 пикселей."}
                return templates.TemplateResponse("core/profile.html",
                                                  {"request": request, "user": user, "profile": profile,
                                                   "alert": alert})
        except Exception:
            alert = {"kind": "error", "text": "Файл не распознан как изображение."}
            return templates.TemplateResponse("core/profile.html",
                                              {"request": request, "user": user, "profile": profile, "alert": alert})

        # 4) Готовим имя файла и удаляем старый, чтобы не копились
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        ext = os.path.splitext(avatar.filename)[1].lower()[:8] or ".jpg"
        # сохраняем под фиксированным именем на пользователя — это ЗАТРЁТ старый файл:
        filename = f"user_{user.id}{ext}"
        dst = AVATAR_DIR / filename

        # если был другой файл — удалим его (любой ext)
        if profile.avatar:
            try:
                (STATIC_DIR / profile.avatar).unlink(missing_ok=True)
            except Exception:
                pass

        dst.write_bytes(content)
        updates["avatar"] = f"uploads/avatars/{filename}"
        log.info({"event": "avatar_saved", "user_id": user.id, "path": updates["avatar"]})

    await repo.update_profile(session, profile_id=profile.id, **updates)
    await session.commit()
    log.info({"event": "profile_updated", "user_id": user.id, "fields": [k for k, v in updates.items() if v is not None]})

    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/profile/avatar/delete", name="profile_avatar_delete")
async def profile_avatar_delete(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    """Удаляет файл аватара и сбрасывает поле avatar в NULL."""
    email = _require_logged_in(request)
    if not email:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    repo = UserRepository()
    user = await repo.get_by_email(session, email=email)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    profile = await repo.get_profile_by_user_id(session, user_id=user.id)
    if not profile:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    if profile.avatar:
        path = (STATIC_DIR / profile.avatar).resolve()
        try:
            if str(path).startswith(str(AVATAR_DIR.resolve())) and path.exists():
                path.unlink()
                log.info({"event": "avatar_deleted", "user_id": user.id, "path": str(path)})
        except Exception as e:
            log.info({"event": "avatar_delete_failed", "user_id": user.id, "error": str(e)})

    await repo.update_profile(session, profile_id=profile.id, avatar=None)
    await session.commit()

    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
