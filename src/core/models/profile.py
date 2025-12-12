# /src/core/models/profile.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint, Integer
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

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),  # удалить профиль при удалении юзера
        nullable=False,
        unique=True,
        index=True,
    )

    # 1:1 с User
    user: Mapped["User"] = relationship("User", back_populates="profile")

    # 1:1 с Permission (singular). delete-orphan: удаляем права вместе с профилем.
    permission: Mapped[Optional["Permission"]] = relationship(
        "Permission",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
    )
