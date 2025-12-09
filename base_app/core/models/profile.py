# /base_app/core/models/profile.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Profile(Base):
    """
    Профиль пользователя (1:1 с users по user_id).
    """
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_profiles_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nickname: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    avatar: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    first_name: Mapped[Optional[str]] = mapped_column(String(48), default=None)
    second_name: Mapped[Optional[str]] = mapped_column(String(48), default=None)
    phone: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    email: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, default=None)
    tg_nickname: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    verification: Mapped[bool] = mapped_column(Boolean, default=False)
    session: Mapped[Optional[str]] = mapped_column(String(255), default=None)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # back_populates с User.profile
    user: Mapped["User"] = relationship("User", back_populates="profile")

    # права (1:many)
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        back_populates="profile",
        cascade="all, delete-orphan",
    )
