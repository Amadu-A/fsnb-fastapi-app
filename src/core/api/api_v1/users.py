# path: src/core/api/api_v1/users.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_user_repository
from src.core.models.db_helper import db_helper
from src.core.schemas.user import UserCreate, UserRead
from src.core.security import hash_password
from src.crud.user_repository import IUserRepository


router = APIRouter(tags=["Users"])


@router.get("", response_model=list[UserRead])
async def get_users(
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
):
    """
    Список пользователей.

    Важно:
    - чтение из БД только через репозиторий;
    - DI отдаёт интерфейс IUserRepository.
    """
    users = await user_repo.list_users(session)
    return list(users)


@router.post("", response_model=UserRead)
async def create_user(
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
    user_create: UserCreate,
):
    """
    Создать пользователя.

    Важно:
    - репозиторий принимает hashed_password (хэширование — не DB-операция);
    - DB-операции только через repo.
    """
    email = user_create.email.strip().lower()
    existing = await user_repo.get_by_email(session, email=email)
    if existing:
        # В реальном API можно вернуть 400/409, но ты просил “не ломать логику” —
        # поэтому оставляем такой же смысл ошибки, как в старых функциях.
        raise ValueError("email_already_exists")

    user = await user_repo.create_user_with_profile_and_permission(
        session,
        email=email,
        hashed_password=hash_password(user_create.password),
    )
    await session.flush()
    return user
