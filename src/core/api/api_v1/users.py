# src/core/api/api_v1/users.py
from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import db_helper
from src.core.schemas.user import UserRead, UserCreate
from src.crud import user_repository as users_crud

router = APIRouter(tags=["Users"])


@router.get("", response_model=list[UserRead])
async def get_users(
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
):
    # функция появится в user_repository (см. ниже)
    users = await users_crud.get_all_users(session=session)
    return users


@router.post("", response_model=UserRead)
async def create_user(
    session: Annotated[AsyncSession, Depends(db_helper.session_getter)],
    user_create: UserCreate,
):
    # тонкая обёртка над репозиторием: создаём User+Profile+Permission
    user = await users_crud.create_user(session=session, user_create=user_create)
    return user
