# /src/core/models/permission.py
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
# Для тайпхинтов не импортируем Profile во время рантайма, чтобы не ловить цикл.
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#     from .profile import Profile


class Permission(Base):
    """
    Набор флагов доступа для профиля.
    Связь: 1:1 с Profile (через unique profile_id).
    """
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # 1:1 с профилем
        index=True,
    )

    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_updater: Mapped[bool] = mapped_column(Boolean, default=False)
    is_reader: Mapped[bool] = mapped_column(Boolean, default=False)
    is_user: Mapped[bool] = mapped_column(Boolean, default=False)

    # Имя поля в Profile — 'permission' (singular)
    profile: Mapped["Profile"] = relationship("Profile", back_populates="permission")

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
