# path: src/train/utils/access.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.permission_repository import PermissionRepository


def require_logged_in_session(request: Request) -> None:
    """
    Для web/Jinja мы используем cookie-session.
    Считаем, что логин кладёт:
      - user_id
      - user_email
      - access_token (JWT, но для HTML нам достаточно user_id/email)
    """
    user_id = request.session.get("user_id")
    user_email = request.session.get("user_email")
    if not user_id or not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_actor_identity(request: Request) -> Dict[str, Any]:
    """
    Единый формат “кто совершил действие”.
    """
    require_logged_in_session(request)
    return {
        "user_id": int(request.session["user_id"]),
        "email": str(request.session["user_email"]),
    }


async def is_actor_editor(session: AsyncSession, actor_user_id: int) -> bool:
    """
    editor = is_superadmin | is_admin | is_staff | is_updater
    """
    repo = PermissionRepository()
    perm = await repo.get_for_user_id(session=session, user_id=int(actor_user_id))
    if not perm:
        return False
    return bool(getattr(perm, "is_superadmin", False) or getattr(perm, "is_admin", False)
                or getattr(perm, "is_staff", False) or getattr(perm, "is_updater", False))
