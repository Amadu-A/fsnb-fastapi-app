# /src/core/schemas/user.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    username: str | None = None
    foo: int = 0
    bar: int = 0


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
