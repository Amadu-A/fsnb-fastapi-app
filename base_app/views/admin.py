from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.logging import get_logger
from base_app.core.models import db_helper
from base_app.core.models.user import User
from base_app.core.models.profile import Profile
from base_app.core.models.permission import Permission
from base_app.core.security import verify_password

router = APIRouter()
log = get_logger("views.admin")

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ensure_csrf(request: Request) -> str:
    token = request.session.get("admin_csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        request.session["admin_csrf"] = token
    return token


def _admin_identity(request: Request) -> Optional[int]:
    return request.session.get("admin_user_id")


async def _require_admin(request: Request, session: AsyncSession) -> Optional[User]:
    admin_uid = _admin_identity(request)
    if not admin_uid:
        return None

    u = await session.get(User, admin_uid)
    if not u:
        return None

    prof = (await session.execute(select(Profile).where(Profile.user_id == u.id))).scalar_one_or_none()
    if not prof:
        return None

    perm = (await session.execute(select(Permission).where(Permission.profile_id == prof.id))).scalar_one_or_none()
    if not perm or not (perm.is_superadmin or perm.is_admin):
        return None

    return u


@router.get("/admin/login", name="admin_login")
async def admin_login_get(request: Request):
    csrf = _ensure_csrf(request)
    return templates.TemplateResponse("admin/login.html", {"request": request, "csrf": csrf})


@router.post("/admin/login", name="admin_login_post")
async def admin_login_post(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    username: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    csrf_token: Annotated[str, Form(...)],
):
    if csrf_token != request.session.get("admin_csrf"):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "csrf": _ensure_csrf(request), "alert": {"kind": "error", "text": "CSRF error"}},
            status_code=400,
        )
    username = (username or "").strip()
    q = await session.execute(select(User).where(User.username == username))
    user = q.scalar_one_or_none()
    if not user or not verify_password(password or "", user.hashed_password or ""):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "csrf": _ensure_csrf(request), "alert": {"kind": "error", "text": "Invalid creds"}},
            status_code=400,
        )

    prof = (await session.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    perm: Optional[Permission] = None
    if prof:
        perm = (await session.execute(select(Permission).where(Permission.profile_id == prof.id))).scalar_one_or_none()

    if not perm or not (perm.is_superadmin or perm.is_admin):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "csrf": _ensure_csrf(request), "alert": {"kind": "error", "text": "No admin rights"}},
            status_code=403,
        )

    request.session["admin_user_id"] = user.id
    log.info({"event": "admin_login_ok", "user_id": user.id, "username": username})
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/logout", name="admin_logout")
async def admin_logout_post(request: Request):
    request.session.pop("admin_user_id", None)
    return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin", name="admin_index")
async def admin_index(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        "admin/index.html",
        {"request": request, "me": me, "models": ["Users", "Profiles", "Permissions"]},
    )


# ---------- Users list ----------
@router.get("/admin/users", name="admin_users")
async def admin_users(request: Request, session: Annotated[AsyncSession, Depends(db_helper.session_getter)]):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    rows = await session.execute(
        select(User, Profile.verification)
        .join(Profile, Profile.user_id == User.id, isouter=True)
        .order_by(User.id)
    )
    items = [{"user": u, "verified": bool(ver)} for (u, ver) in rows.all()]

    return templates.TemplateResponse("admin/users.html", {"request": request, "items": items})


# ---------- Unified User/Profile/Permissions edit ----------
@router.get("/admin/users/{user_id}/edit", name="admin_user_edit_get")
async def admin_user_edit_get(
    request: Request,
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    # Целевой пользователь
    user = await session.get(User, user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    # Профиль: создадим, если нет
    profile = (await session.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    if not profile:
        profile = Profile(user_id=user.id)
        session.add(profile)
        await session.commit()
        log.info({"event": "admin_autocreate_profile", "user_id": user.id, "profile_id": profile.id})

    # Права: создадим, если нет
    perm = (await session.execute(select(Permission).where(Permission.profile_id == profile.id))).scalar_one_or_none()
    if not perm:
        perm = Permission(profile_id=profile.id)  # все False по умолчанию
        session.add(perm)
        await session.commit()
        log.info({"event": "admin_autocreate_permission", "profile_id": profile.id, "permission_id": perm.id})

    # Права актёра
    me_prof = (await session.execute(select(Profile).where(Profile.user_id == me.id))).scalar_one_or_none()
    me_perm = None
    if me_prof:
        me_perm = (await session.execute(select(Permission).where(Permission.profile_id == me_prof.id))).scalar_one_or_none()

    is_actor_super = bool(me_perm and me_perm.is_superadmin)
    is_actor_admin = bool(me_perm and me_perm.is_admin)

    # Можно ли редактировать блок прав?
    perm_editable = True
    perm_note = None
    if (perm and perm.is_superadmin) and is_actor_admin and not is_actor_super:
        # admin не может редактировать супер-админа
        perm_editable = False
        perm_note = "Нельзя редактировать права суперпользователя, имея только роль admin."
    can_edit_super_flag = is_actor_super  # можно ли трогать чекбокс is_superadmin

    csrf = _ensure_csrf(request)
    return templates.TemplateResponse(
        "admin/user_edit.html",
        {
            "request": request,
            "csrf": csrf,
            "user": user,
            "profile": profile,
            "perm": perm,
            "perm_editable": perm_editable,
            "can_edit_super_flag": can_edit_super_flag,
            "perm_note": perm_note,
        },
    )


@router.post("/admin/users/{user_id}/edit", name="admin_user_edit_post")
async def admin_user_edit_post(
    request: Request,
    user_id: int,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    csrf_token: Annotated[str, Form(...)],

    # --- User ---
    username: Annotated[str | None, Form()] = None,
    is_active: Annotated[str | None, Form()] = None,

    # --- Profile ---
    nickname: Annotated[str | None, Form()] = None,
    first_name: Annotated[str | None, Form()] = None,
    second_name: Annotated[str | None, Form()] = None,
    phone: Annotated[str | None, Form()] = None,
    email: Annotated[str | None, Form()] = None,
    tg_id: Annotated[str | None, Form()] = None,
    tg_nickname: Annotated[str | None, Form()] = None,
    verification: Annotated[str | None, Form()] = None,

    # --- Permissions ---
    is_superadmin: Annotated[str | None, Form()] = None,
    is_admin_flag: Annotated[str | None, Form()] = None,   # чтобы не конфликтовало с импортом is_admin var
    is_staff: Annotated[str | None, Form()] = None,
    is_updater: Annotated[str | None, Form()] = None,
    is_reader: Annotated[str | None, Form()] = None,
    is_user_flag: Annotated[str | None, Form()] = None,
):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    if csrf_token != request.session.get("admin_csrf"):
        return RedirectResponse(url=f"/admin/users/{user_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    # Цель
    user = await session.get(User, user_id)
    if not user:
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

    profile = (await session.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    if not profile:
        profile = Profile(user_id=user.id)
        session.add(profile)
        await session.flush()  # получим id без полного commit
        log.info({"event": "admin_autocreate_profile", "user_id": user.id, "profile_id": profile.id})

    perm = (await session.execute(select(Permission).where(Permission.profile_id == profile.id))).scalar_one_or_none()
    if not perm:
        perm = Permission(profile_id=profile.id)
        session.add(perm)
        await session.flush()
        log.info({"event": "admin_autocreate_permission", "profile_id": profile.id, "permission_id": perm.id})

    # Права актёра
    me_prof = (await session.execute(select(Profile).where(Profile.user_id == me.id))).scalar_one_or_none()
    me_perm = None
    if me_prof:
        me_perm = (await session.execute(select(Permission).where(Permission.profile_id == me_prof.id))).scalar_one_or_none()
    is_actor_super = bool(me_perm and me_perm.is_superadmin)
    is_actor_admin = bool(me_perm and me_perm.is_admin)

    # --- Готовим апдейты
    user_vals: dict[str, object] = {}
    if username is not None:
        user_vals["username"] = (username.strip() or None)

    # ⬇️ Всегда пишем булево, даже если чекбокс снят (is_active == None)
    user_vals["is_active"] = (is_active == "on")

    profile_vals: dict[str, object] = {}
    for k, v in [
        ("nickname", nickname),
        ("first_name", first_name),
        ("second_name", second_name),
        ("phone", phone),
        ("email", email),
        ("tg_nickname", tg_nickname),
    ]:
        if v is not None:
            profile_vals[k] = (v.strip() or None)

    # tg_id — аккуратно к int
    if tg_id is not None:
        tg_id_val: Optional[int]
        t = tg_id.strip()
        if t == "":
            tg_id_val = None
        else:
            try:
                tg_id_val = int(t)
            except ValueError:
                tg_id_val = None
        profile_vals["tg_id"] = tg_id_val

    # ⬇️ Всегда пишем булево для verification
    profile_vals["verification"] = (verification == "on")

    # permissions
    perm_vals: dict[str, bool] = {
        "is_superadmin": (is_superadmin == "on"),
        "is_admin": (is_admin_flag == "on"),
        "is_staff": (is_staff == "on"),
        "is_updater": (is_updater == "on"),
        "is_reader": (is_reader == "on"),
        "is_user": (is_user_flag == "on"),
    }

    # Если актор не супер — запрещаем менять флаг суперпользователя
    if not is_actor_super:
        perm_vals.pop("is_superadmin", None)

    # Если актор — admin (не супер) и цель — супер, не трогаем права вообще
    if (perm.is_superadmin) and is_actor_admin and not is_actor_super:
        perm_vals.clear()

    # --- Применяем
    if user_vals:
        await session.execute(update(User).where(User.id == user.id).values(**user_vals))
        log.info({"event": "admin_user_update", "actor_id": me.id, "target_user_id": user.id, **user_vals})

    if profile_vals:
        await session.execute(update(Profile).where(Profile.id == profile.id).values(**profile_vals))
        log.info({"event": "admin_profile_update", "actor_id": me.id, "target_profile_id": profile.id, **profile_vals})

    if perm_vals:
        await session.execute(update(Permission).where(Permission.profile_id == profile.id).values(**perm_vals))
        log.info({"event": "admin_perm_update", "actor_id": me.id, "target_profile_id": profile.id, **perm_vals})

    await session.commit()
    return RedirectResponse(url=f"/admin/users/{user.id}/edit", status_code=status.HTTP_303_SEE_OTHER)
