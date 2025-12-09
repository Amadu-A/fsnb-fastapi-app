# /base_app/views/web.py
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Request
from fastapi.params import Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from base_app.core.logging import get_logger
from base_app.core.models import db_helper
from base_app.crud import users as users_crud

router = APIRouter()  # без префикса — это корневые HTML-страницы
log = get_logger("web")

# Путь к папке templates/ в корне проекта
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))




@router.get("/", name="home")
async def home(request: Request):
    """
    Главная страница. Возвращает templates/index.html.
    """
    log.info({"event": "open_page", "path": "/", "method": "GET"})
    return templates.TemplateResponse(
        "core/index.html",
        {"request": request},
    )


@router.get("/users/", name="users_list_html")
async def users_list_html(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    """
    Список пользователей из БД — templates/users/list.html.
    """
    users = await users_crud.get_all_users(session=session)
    log.info({
        "event": "open_page",
        "path": "/users/",
        "method": "GET",
        "count": len(users),
    })
    return templates.TemplateResponse(
        "users/list.html",
        {"request": request, "users": users},
    )
