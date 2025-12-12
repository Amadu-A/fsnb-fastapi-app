# src/core/models/user.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    """
    Базовая модель пользователя.
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # username может быть NULL (мы регистрируем по email)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)

    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    activation_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    activation_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    foo: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    bar: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # 1:1 с Profile
    profile: Mapped["Profile"] = relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("username", name="uq_users_username"),
    )
