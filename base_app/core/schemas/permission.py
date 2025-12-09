# /base_app/core/schemas/permission.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    profile_id: int
    is_superadmin: bool
    is_admin: bool
    is_staff: bool
    is_updater: bool
    is_reader: bool
    is_user: bool
