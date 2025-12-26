# path: src/core/views/admin.py
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated, Optional, Any, Dict
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update, or_, func, delete
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

from src.core.utils import (
    build_pagination,
    coerce_value,
    get_boolean_fields,
    get_columns,
    get_fk_target_table,
)

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

from urllib.parse import urlencode

from sqlalchemy import func, or_, select
from sqlalchemy.inspection import inspect as sa_inspect

# ... остальное уже у тебя есть: coerce_value/build_pagination/get_columns/get_boolean_fields/get_fk_target_table etc.

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
    cols = get_columns(Model)

    # page
    try:
        page = int(request.query_params.get("page", "1"))
    except Exception:
        page = 1
    if page < 1:
        page = 1

    page_size = int(getattr(ma, "page_size", 50) or 50)
    if page_size <= 0:
        page_size = 50
    if page_size > 200:
        page_size = 200  # защита

    stmt = select(Model)
    count_stmt = select(func.count()).select_from(Model)

    # bool fields
    bool_fields = get_boolean_fields(Model)

    # exact filters: любой query param совпал с колонкой -> equality
    # + булевы фильтры all/true/false (как ты задумал в UI)
    for key, raw in request.query_params.items():
        if key in {"page", "q"}:
            continue
        if key not in cols:
            continue
        if raw is None or str(raw).strip() == "":
            continue

        # булевы фильтры: true/false
        if key in bool_fields:
            b = parse_bool(raw)
            if b is None:
                continue
            stmt = stmt.where(getattr(Model, key) == b)
            count_stmt = count_stmt.where(getattr(Model, key) == b)
            continue

        val = coerce_value(cols[key], raw)
        if val is None:
            continue
        stmt = stmt.where(getattr(Model, key) == val)
        count_stmt = count_stmt.where(getattr(Model, key) == val)

    # search
    q = (q or "").strip()
    if q and ma.search_fields:
        clauses = []
        for f in ma.search_fields:
            if f in cols:
                clauses.append(getattr(Model, f).ilike(f"%{q}%"))
        if clauses:
            stmt = stmt.where(or_(*clauses))
            count_stmt = count_stmt.where(or_(*clauses))

    total = (await session.execute(count_stmt)).scalar_one()
    pagination = build_pagination(total=total, page=page, page_size=page_size)

    # ordering:
    # 1) created_at desc если есть
    # 2) если есть одиночный id — по id desc
    # 3) если нет id (например training_run_rows) — по всем PK desc
    if "created_at" in cols:
        stmt = stmt.order_by(getattr(Model, "created_at").desc())
    else:
        insp = sa_inspect(Model)
        pk_cols = list(insp.primary_key)
        if pk_cols:
            # training_run_rows: (run_id, row_id) — сортируем стабильно по PK desc
            for pk in pk_cols:
                stmt = stmt.order_by(pk.desc())

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    rows = (await session.execute(stmt)).scalars().all()

    # FK map: field -> target slug (table name), filter by id
    fk_map: dict[str, dict[str, str]] = {}
    for name, col in cols.items():
        target_table = get_fk_target_table(col)
        if not target_table:
            continue
        if admin_site.get(target_table):
            fk_map[name] = {"slug": target_table, "field": "id"}

    # prev/next urls with all current params
    base_params = dict(request.query_params)
    base_params.pop("page", None)

    def make_url(p: int) -> str:
        params = dict(base_params)
        params["page"] = str(p)
        return str(request.url.replace(query=urlencode(params, doseq=True)))

    prev_url = make_url(pagination.prev_page) if pagination.has_prev else None
    next_url = make_url(pagination.next_page) if pagination.has_next else None

    # edit guard:
    # редактируем только если:
    # - в админке включён can_edit
    # - есть ровно 1 PK
    # - этот PK называется "id"
    insp = sa_inspect(Model)
    pk_cols = list(insp.primary_key)
    has_edit = bool(getattr(ma, "can_edit", False)) and bool(ma.form_fields) and (len(pk_cols) == 1) and (pk_cols[0].key == "id")
    edit_pk = "id" if has_edit else None

    return templates.TemplateResponse(
        "admin/model_list.html",
        {
            "request": request,
            "slug": slug,
            "model_name": Model.__name__,
            "ma": ma,
            "list_display": ma.list_display or [c.key for c in sa_inspect(Model).columns],
            "rows": rows,
            "q": q,
            "bool_fields": bool_fields,
            "fk_map": fk_map,
            "pagination": pagination,
            "prev_url": prev_url,
            "next_url": next_url,
            "csrf": _ensure_csrf(request),
            "has_edit": has_edit,
            "edit_pk": edit_pk,
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

    # (если ты добавлял can_edit) — защита read-only
    if hasattr(ma, "can_edit") and not ma.can_edit:
        raise HTTPException(status_code=403, detail="Read-only model")

    Model = ma.model
    obj = await session.get(Model, obj_id)
    if not obj:
        return RedirectResponse(url=f"/admin/m/{slug}", status_code=status.HTTP_303_SEE_OTHER)

    csrf = _ensure_csrf(request)

    me_prof = await profile_repo.get_by_user_id(session, user_id=int(me.id))
    me_perm = await permission_repo.get_by_profile_id(session, profile_id=int(me_prof.id)) if me_prof else None
    can_edit_super_flag = bool(me_perm and getattr(me_perm, "is_superadmin", False))

    # ✅ fk_map для ссылок на связанные таблицы
    cols = get_columns(Model)
    fk_map: dict[str, dict[str, str]] = {}
    for name, col in cols.items():
        target_table = get_fk_target_table(col)
        if not target_table:
            continue
        # в админке slug обычно = __tablename__ => target_table
        if admin_site.get(target_table):
            fk_map[name] = {"slug": target_table, "field": "id"}

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
            "fk_map": fk_map,  # ✅ ВОТ ЭТОГО НЕ ХВАТАЛО
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
    if hasattr(ma, "can_edit") and not ma.can_edit:
        raise HTTPException(status_code=403, detail="Read-only model")

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
    me_prof = await profile_repo.get_by_user_id(session, user_id=int(me.id))
    me_perm = None
    if me_prof:
        me_perm = await permission_repo.get_by_profile_id(session, profile_id=int(me_prof.id)) if me_prof else None
    actor_is_super = bool(me_perm and getattr(me_perm, "is_superadmin", False))

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


@router.post("/admin/m/{slug}/clear", name="admin_model_clear")
async def admin_model_clear(
    request: Request,
    slug: str,
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
        raise HTTPException(status_code=400, detail="CSRF error")

    ma = admin_site.get(slug)
    if not ma:
        raise HTTPException(status_code=404, detail="Model not registered")
    if not getattr(ma, "can_delete", False):
        raise HTTPException(status_code=403, detail="Clear not allowed")

    await session.execute(delete(ma.model))
    await session.commit()

    return RedirectResponse(url=f"/admin/m/{slug}", status_code=status.HTTP_303_SEE_OTHER)
