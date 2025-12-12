# /src/core/views/admin.py
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

from src.logging import get_logger
from src.core.models import db_helper
from src.core.models.user import User
from src.core.models.profile import Profile
from src.core.models.permission import Permission
from src.core.security import verify_password
from src.admin import admin_site

router = APIRouter()
log = get_logger("views.admin")

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# ДАДИМ Jinja функцию attr(obj, name) = getattr(obj, name, None)
templates.env.globals.update(attr=lambda o, n: getattr(o, n, None))


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


# ------------- ЛОГИН/ЛОГАУТ -------------

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
    perm = None
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


# ------------- ИНДЕКС -------------

@router.get("/admin", name="admin_index")
async def admin_index(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    # модели из реестра
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
    q: str | None = None,
):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")

    Model = ma.model
    stmt = select(Model)

    # Поиск
    if q and ma.search_fields:
        insp = sa_inspect(Model)
        clauses = []
        for f in ma.search_fields:
            col = getattr(Model, f, None)
            if col is not None:
                clauses.append(getattr(Model, f).ilike(f"%{q}%"))
        if clauses:
            stmt = stmt.where(or_(*clauses))

    # Сортировка по первичному ключу
    insp = sa_inspect(Model)
    pk_cols = insp.primary_key
    if pk_cols:
        stmt = stmt.order_by(pk_cols[0])

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
    # пустые строки -> None
    if raw.strip() == "":
        return None

    t = col.type.__class__.__name__.lower()
    try:
        if "boolean" in t:
            # чекбоксы обрабатываем отдельно, сюда редко попадем
            return raw.lower() in ("1", "true", "on", "yes")
        if "integer" in t or "bigint" in t or "smallint" in t:
            return int(raw)
        if "float" in t or "numeric" in t or "decimal" in t:
            return float(raw)
        # даты/датавремя можно разобрать позже ISO-строкой — оставим строкой
        return raw
    except Exception:
        return raw


@router.get("/admin/m/{slug}/{obj_id}/edit", name="admin_model_edit")
async def admin_model_edit_get(
    request: Request,
    slug: str,
    obj_id: int,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")

    Model = ma.model
    obj = await session.get(Model, obj_id)
    if not obj:
        return RedirectResponse(url=f"/admin/m/{slug}", status_code=status.HTTP_303_SEE_OTHER)

    csrf = _ensure_csrf(request)

    # для чекбокса is_superadmin: редактировать может только супер
    me_prof = (await session.execute(select(Profile).where(Profile.user_id == me.id))).scalar_one_or_none()
    me_perm = None
    if me_prof:
        me_perm = (await session.execute(select(Permission).where(Permission.profile_id == me_prof.id))).scalar_one_or_none()
    can_edit_super_flag = bool(me_perm and me_perm.is_superadmin)

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
    csrf_token: Annotated[str, Form(...)],
):
    me = await _require_admin(request, session)
    if not me:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    if csrf_token != request.session.get("admin_csrf"):
        return RedirectResponse(url=f"/admin/m/{slug}/{obj_id}/edit", status_code=status.HTTP_303_SEE_OTHER)

    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")

    Model = ma.model
    obj = await session.get(Model, obj_id)
    if not obj:
        return RedirectResponse(url=f"/admin/m/{slug}", status_code=status.HTTP_303_SEE_OTHER)

    insp = sa_inspect(Model)
    columns: Dict[str, Column] = {c.key: c for c in insp.columns}
    vals: Dict[str, Any] = {}

    # Права на редактирование супер-флага
    me_prof = (await session.execute(select(Profile).where(Profile.user_id == me.id))).scalar_one_or_none()
    me_perm = None
    if me_prof:
        me_perm = (await session.execute(select(Permission).where(Permission.profile_id == me_prof.id))).scalar_one_or_none()
    actor_is_super = bool(me_perm and me_perm.is_superadmin)

    # Чекбоксы: соберём все как presence->bool
    # Остальные поля читаем через _coerce_value
    for f in ma.form_fields:
        if f not in columns:
            continue
        col = columns[f]
        tname = col.type.__class__.__name__.lower()
        if "boolean" in tname:
            raw = (await request.form()).get(f)  # "on" или None
            vals[f] = bool(raw == "on")
        else:
            raw = (await request.form()).get(f)
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
