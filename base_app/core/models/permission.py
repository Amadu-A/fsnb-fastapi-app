# /base_app/core/models/permission.py
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
# ВАЖНО: НЕ импортируем Profile здесь во время рантайма, чтобы не ловить цикл.
# Для тайпхинтов можно так:
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .profile import Profile


class Permission(Base):
    """
    Набор флагов доступа для профиля (many-to-one с Profile).
    По умолчанию — всё False.
    """
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)

    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_updater: Mapped[bool] = mapped_column(Boolean, default=False)
    is_reader: Mapped[bool] = mapped_column(Boolean, default=False)
    is_user: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="permissions")

    def verificate(self) -> None:
        """
        Если профиль не верифицирован — сбрасываем все флаги прав.
        """
        if not self.profile or not self.profile.verification:
            self.is_superadmin = False
            self.is_admin = False
            self.is_staff = False
            self.is_updater = False
            self.is_reader = False
            self.is_user = False
