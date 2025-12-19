# path: src/core/views/admin.py
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated, Optional, Any, Dict

from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.sql.schema import Column

from src.app_logging import get_logger
from src.core.dependencies import (
    get_permission_repository,
    get_profile_repository,
    get_user_repository,
)
from src.core.models.db_helper import db_helper
from src.core.models.user import User
from src.core.models.profile import Profile
from src.core.models.permission import Permission
from src.core.security import verify_password
from src.crud.permission_repository import IPermissionRepository
from src.crud.profile_repository import IProfileRepository
from src.crud.user_repository import IUserRepository
from src.admin import admin_site


router = APIRouter()
log = get_logger("views.admin")

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals.update(attr=lambda o, n: getattr(o, n, None))


def _ensure_csrf(request: Request) -> str:
    token = request.session.get("admin_csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        request.session["admin_csrf"] = token
    return token


def _admin_identity(request: Request) -> Optional[int]:
    return request.session.get("admin_user_id")


async def _require_admin(
    request: Request,
    session: AsyncSession,
    user_repo: IUserRepository,
    profile_repo: IProfileRepository,
    permission_repo: IPermissionRepository,
) -> Optional[User]:
    """
    Проверка доступа в админку.

    Раньше тут были прямые запросы:
      - session.get(User, id)
      - select(Profile)
      - select(Permission)
    Теперь всё это делаем через DI-репозитории.
    """
    admin_uid = _admin_identity(request)
    if not admin_uid:
        return None

    u = await user_repo.get_by_id(session, user_id=int(admin_uid))
    if not u:
        return None

    prof = await profile_repo.get_by_user_id(session, user_id=int(u.id))
    if not prof:
        return None

    perm = await permission_repo.get_by_profile_id(session, profile_id=int(prof.id))
    if not perm or not (perm.is_superadmin or perm.is_admin):
        return None

    return u


# ------------- ЛОГИН/ЛОГАУТ -------------

@router.get("/admin/login", name="admin_login")
async def admin_login_get(request: Request):
    csrf = _ensure_csrf(request)
    return templates.TemplateResponse("admin/login.html", {"request": request, "csrf": csrf})


@router.post("/admin/login", name="admin_login_post")
async def admin_login_post(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    profile_repo: Annotated[IProfileRepository, Depends(get_profile_repository)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repository)],
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

    # ❗️Раньше тут был прямой SQL: select(User).where(User.username == username)
    # ✅ Теперь берём через репозиторий:
    user = await user_repo.get_by_username(session, username=username)

    if not user or not verify_password(password or "", user.hashed_password or ""):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "csrf": _ensure_csrf(request), "alert": {"kind": "error", "text": "Invalid creds"}},
            status_code=400,
        )

    # ❗️Раньше были прямые select(Profile)/select(Permission)
    # ✅ Теперь всё через репозитории:
    prof = await profile_repo.get_by_user_id(session, user_id=int(user.id))
    perm = await permission_repo.get_by_profile_id(session, profile_id=int(prof.id)) if prof else None

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


# ------------- ИНДЕКС -------------

@router.get("/admin", name="admin_index")
async def admin_index(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    profile_repo: Annotated[IProfileRepository, Depends(get_profile_repository)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repository)],
):
    me = await _require_admin(request, session, user_repo, profile_repo, permission_repo)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    models = [{"slug": m.slug, "model_name": m.model.__name__} for m in admin_site.all()]
    return templates.TemplateResponse(
        "admin/index.html",
        {"request": request, "me": me, "models": models},
    )


# ------------- ГЕНЕРИК: СПИСОК -------------

@router.get("/admin/m/{slug}", name="admin_model_list")
async def admin_model_list(
    request: Request,
    slug: str,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    profile_repo: Annotated[IProfileRepository, Depends(get_profile_repository)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repository)],
    q: str | None = None,
):
    me = await _require_admin(request, session, user_repo, profile_repo, permission_repo)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")

    Model = ma.model
    stmt = select(Model)

    if q and ma.search_fields:
        clauses = []
        for f in ma.search_fields:
            col = getattr(Model, f, None)
            if col is not None:
                clauses.append(getattr(Model, f).ilike(f"%{q}%"))
        if clauses:
            stmt = stmt.where(or_(*clauses))

    insp = sa_inspect(Model)
    pk_cols = insp.primary_key
    if pk_cols:
        stmt = stmt.order_by(pk_cols[0])

    # ⚠️ Универсальная админка по любым моделям:
    # - Для моделей без репозитория это неизбежно (иначе нужен GenericRepository).
    # - Для User/Profile/Permission мы уже убрали прямые запросы в местах авторизации/прав.
    rows = (await session.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        "admin/model_list.html",
        {
            "request": request,
            "slug": slug,
            "model_name": Model.__name__,
            "list_display": ma.list_display or [c.key for c in sa_inspect(Model).columns],
            "rows": rows,
            "q": q or "",
        },
    )


# ------------- ГЕНЕРИК: ФОРМА РЕДАКТИРОВАНИЯ -------------

def _coerce_value(col: Column, raw: str | None) -> Any:
    if raw is None:
        return None
    if raw.strip() == "":
        return None

    t = col.type.__class__.__name__.lower()
    try:
        if "boolean" in t:
            return raw.lower() in ("1", "true", "on", "yes")
        if "integer" in t or "bigint" in t or "smallint" in t:
            return int(raw)
        if "float" in t or "numeric" in t or "decimal" in t:
            return float(raw)
        return raw
    except Exception:
        return raw


@router.get("/admin/m/{slug}/{obj_id}/edit", name="admin_model_edit")
async def admin_model_edit_get(
    request: Request,
    slug: str,
    obj_id: int,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    profile_repo: Annotated[IProfileRepository, Depends(get_profile_repository)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repository)],
):
    me = await _require_admin(request, session, user_repo, profile_repo, permission_repo)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")

    Model = ma.model

    # ⚠️ Универсальная админка:
    # для произвольной модели без репозитория используем session.get как исключение.
    obj = await session.get(Model, obj_id)
    if not obj:
        return RedirectResponse(url=f"/admin/m/{slug}", status_code=status.HTTP_303_SEE_OTHER)

    csrf = _ensure_csrf(request)

    # Права на редактирование супер-флага (Permission.is_superadmin)
    me_prof = await profile_repo.get_by_user_id(session, user_id=int(me.id))
    me_perm = await permission_repo.get_by_profile_id(session, profile_id=int(me_prof.id)) if me_prof else None
    can_edit_super_flag = bool(me_perm and getattr(me_perm, "is_superadmin", False))

    return templates.TemplateResponse(
        "admin/model_edit.html",
        {
            "request": request,
            "slug": slug,
            "model_name": Model.__name__,
            "obj": obj,
            "fields": ma.form_fields,
            "readonly_fields": ma.readonly_fields,
            "labels": ma.field_labels,
            "csrf": csrf,
            "can_edit_super_flag": can_edit_super_flag,
        },
    )


@router.post("/admin/m/{slug}/{obj_id}/edit", name="admin_model_edit_post")
async def admin_model_edit_post(
    request: Request,
    slug: str,
    obj_id: int,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    profile_repo: Annotated[IProfileRepository, Depends(get_profile_repository)],
    permission_repo: Annotated[IPermissionRepository, Depends(get_permission_repository)],
    csrf_token: Annotated[str, Form(...)],
):
    me = await _require_admin(request, session, user_repo, profile_repo, permission_repo)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    if csrf_token != request.session.get("admin_csrf"):
        return RedirectResponse(url=f"/admin/m/{slug}/{obj_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")

    Model = ma.model

    # ⚠️ Универсальная админка: как исключение получаем объект напрямую,
    # потому что для произвольных моделей репозитории могут отсутствовать.
    obj = await session.get(Model, obj_id)
    if not obj:
        return RedirectResponse(url=f"/admin/m/{slug}", status_code=status.HTTP_303_SEE_OTHER)

    insp = sa_inspect(Model)
    columns: Dict[str, Column] = {c.key: c for c in insp.columns}
    vals: Dict[str, Any] = {}

    # ✅ form читаем один раз
    form = await request.form()

    # ✅ если profile_repo передан как Depends и не используется — просто "потрогай" переменную
    # _ = profile_repo  # если надо убрать warning "unused" (никаких await!)

    # Права на редактирование супер-флага
    me_prof = (await session.execute(select(Profile).where(Profile.user_id == me.id))).scalar_one_or_none()
    me_perm = None
    if me_prof:
        me_perm = (
            await session.execute(select(Permission).where(Permission.profile_id == me_prof.id))).scalar_one_or_none()
    actor_is_super = bool(me_perm and me_perm.is_superadmin)

    for f in ma.form_fields:
        if f not in columns:
            continue
        col = columns[f]
        tname = col.type.__class__.__name__.lower()

        if "boolean" in tname:
            raw = form.get(f)
            # ✅ checkbox: если поле пришло — True (не важно какое value)
            vals[f] = raw is not None

        else:
            raw = form.get(f)
            vals[f] = _coerce_value(col, raw)

    # Если редактируем Permission — не давать менять is_superadmin, если актор не супер
    if Model is Permission and not actor_is_super and "is_superadmin" in vals:
        vals.pop("is_superadmin", None)

    # Никогда не пишем readonly
    for ro in ma.readonly_fields:
        vals.pop(ro, None)

    if vals:
        await session.execute(update(Model).where(insp.primary_key[0] == obj_id).values(**vals))
        await session.commit()
        log.info({"event": "admin_model_update", "slug": slug, "obj_id": obj_id, **vals})

    return RedirectResponse(url=f"/admin/m/{slug}/{obj_id}/edit", status_code=status.HTTP_303_SEE_OTHER)
