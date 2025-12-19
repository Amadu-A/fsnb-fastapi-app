# path: src/core/views/web.py
from __future__ import annotations

import io
from pathlib import Path
from typing import Annotated, Optional

from PIL import Image
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.app_logging import get_logger
from src.core.dependencies import get_user_repository
from src.core.models import db_helper
from src.crud.user_repository import IUserRepository

router = APIRouter()
log = get_logger("web")

PROJECT_DIR = Path(__file__).resolve().parents[3]   # /app
SRC_DIR = PROJECT_DIR / "src"

TEMPLATES_DIR = SRC_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATIC_DIR = PROJECT_DIR / "static"
AVATAR_DIR = STATIC_DIR / "uploads" / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)

MAX_AVATAR_MB = 3
MAX_AVATAR_BYTES = MAX_AVATAR_MB * 1024 * 1024
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.get("/", name="home")
async def index_html(request: Request):
    log.info({"event": "open_page", "path": "/", "method": "GET"})
    return templates.TemplateResponse("core/index.html", {"request": request})


@router.get("/users/", name="users_list_html")
async def users_list_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
):
    users = await user_repo.list_users(session)
    log.info({"event": "open_page", "path": "/users/", "method": "GET", "count": len(users)})
    return templates.TemplateResponse("users/list.html", {"request": request, "users": users})


def _require_logged_in(request: Request) -> Optional[str]:
    token = request.session.get("access_token")
    email = request.session.get("user_email")
    if not token or not email:
        return None
    return str(email)


@router.get("/profile", name="profile_html")
async def profile_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
):
    email = _require_logged_in(request)
    if not email:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    user = await user_repo.get_by_email(session, email=email)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    profile = await user_repo.get_profile_by_user_id(session, user_id=int(user.id))

    return templates.TemplateResponse("core/profile.html", {"request": request, "user": user, "profile": profile})


@router.post("/profile", name="profile_post_html")
async def profile_post_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    nickname: Annotated[str | None, Form()] = None,
    first_name: Annotated[str | None, Form()] = None,
    second_name: Annotated[str | None, Form()] = None,
    phone: Annotated[str | None, Form()] = None,
    email_field: Annotated[str | None, Form()] = None,
    tg_id: Annotated[str | None, Form()] = None,
    tg_nickname: Annotated[str | None, Form()] = None,
    avatar: Annotated[UploadFile | None, File()] = None,
):
    def _clean_str(v: str | None) -> str | None:
        if not v:
            return None
        v = v.strip()
        return v or None

    def _clean_tg_id(v: str | None) -> int | None:
        if not v:
            return None
        digits = "".join(ch for ch in v if ch.isdigit())
        return int(digits) if digits else None

    email = _require_logged_in(request)
    if not email:
        return RedirectResponse("/auth/login", status.HTTP_303_SEE_OTHER)

    user = await user_repo.get_by_email(session, email=email)
    if not user:
        return RedirectResponse("/auth/login", status.HTTP_303_SEE_OTHER)

    profile = await user_repo.get_profile_by_user_id(session, user_id=int(user.id))
    if not profile:
        return RedirectResponse("/", status.HTTP_303_SEE_OTHER)

    updates: dict[str, object] = {
        "nickname": _clean_str(nickname),
        "first_name": _clean_str(first_name),
        "second_name": _clean_str(second_name),
        "phone": _clean_str(phone),
        "email": _clean_str(email_field),
        "tg_id": _clean_tg_id(tg_id),
        "tg_nickname": _clean_str(tg_nickname),
    }

    if avatar and avatar.filename:
        if avatar.content_type not in ALLOWED_CONTENT_TYPES:
            return templates.TemplateResponse(
                "core/profile.html",
                {"request": request, "user": user, "profile": profile, "alert": {"kind": "error", "text": "Разрешены только изображения"}},
            )

        content = await avatar.read()
        if len(content) > MAX_AVATAR_BYTES:
            return templates.TemplateResponse(
                "core/profile.html",
                {"request": request, "user": user, "profile": profile, "alert": {"kind": "error", "text": "Максимальный размер — 3 МБ"}},
            )

        try:
            img = Image.open(io.BytesIO(content))
            img.load()
            if img.width < 40 or img.height < 40:
                raise ValueError
        except Exception:
            return templates.TemplateResponse(
                "core/profile.html",
                {"request": request, "user": user, "profile": profile, "alert": {"kind": "error", "text": "Некорректное изображение"}},
            )

        user_dir = AVATAR_DIR / f"user_{int(user.id)}"
        user_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(avatar.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            ext = ".jpg"

        filename = f"user_{int(user.id)}{ext}"
        dst = user_dir / filename

        for old in user_dir.glob("user_*.*"):
            old.unlink(missing_ok=True)

        dst.write_bytes(content)
        updates["avatar"] = f"uploads/avatars/user_{int(user.id)}/{filename}"

        log.info({"event": "avatar_saved", "user_id": int(user.id), "path": updates["avatar"]})

    await user_repo.update_profile(session=session, profile_id=int(profile.id), **updates)
    await session.commit()

    log.info({"event": "profile_updated", "user_id": int(user.id), "fields": list(updates.keys())})
    return RedirectResponse("/profile", status.HTTP_303_SEE_OTHER)


@router.post("/profile/avatar/delete", name="profile_avatar_delete")
async def profile_avatar_delete(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
):
    email = _require_logged_in(request)
    if not email:
        return RedirectResponse("/auth/login", status.HTTP_303_SEE_OTHER)

    user = await user_repo.get_by_email(session, email=email)
    if not user:
        return RedirectResponse("/auth/login", status.HTTP_303_SEE_OTHER)

    profile = await user_repo.get_profile_by_user_id(session, user_id=int(user.id))
    if not profile:
        return RedirectResponse("/", status.HTTP_303_SEE_OTHER)

    if profile.avatar:
        path = (STATIC_DIR / str(profile.avatar)).resolve()

        # ✅ защита от path traversal: удаляем только внутри STATIC_DIR
        if STATIC_DIR.resolve() in path.parents and path.exists():
            path.unlink()

    await user_repo.update_profile(session=session, profile_id=int(profile.id), avatar=None)
    await session.commit()

    return RedirectResponse("/profile", status.HTTP_303_SEE_OTHER)
