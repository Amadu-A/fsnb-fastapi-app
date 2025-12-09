# /base_app/core/schemas/profile.py
from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr

from .permission import PermissionRead


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    email: Optional[EmailStr] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    first_name: Optional[str] = None
    second_name: Optional[str] = None
    phone: Optional[str] = None
    tg_id: Optional[int] = None
    tg_nickname: Optional[str] = None
    verification: bool
    session: Optional[str] = None
    permissions: List[PermissionRead] = []
