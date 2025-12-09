# /base_app/core/models/user.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    """
    Базовый пользователь приложения.
    email — логин (уникален), username — опционально.
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("username", name="uq_users_username"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), default=None)

    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    activation_key: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    activation_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    # для обратной совместимости
    foo: Mapped[int] = mapped_column(default=0)
    bar: Mapped[int] = mapped_column(default=0)

    # 1:1 с Profile
    profile: Mapped[Optional["Profile"]] = relationship("Profile", back_populates="user", uselist=False)
