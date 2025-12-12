# /src/admin.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from sqlalchemy.orm import DeclarativeMeta

from src.core.models.user import User
from src.core.models.profile import Profile
from src.core.models.permission import Permission


@dataclass
class ModelAdmin:
    """
    Описание модели для админки.
    """
    model: Type[DeclarativeMeta]
    slug: str                                     # url-часть, например "users"
    list_display: List[str] = field(default_factory=list)   # колонки в списке
    form_fields: List[str] = field(default_factory=list)    # редактируемые поля
    readonly_fields: List[str] = field(default_factory=list)
    field_labels: Dict[str, str] = field(default_factory=dict)
    search_fields: List[str] = field(default_factory=list)  # поля для поиска
    can_create: bool = False
    can_delete: bool = False


class AdminSite:
    def __init__(self) -> None:
        self._registry: Dict[str, ModelAdmin] = {}

    def register(self, model: Type[DeclarativeMeta], /, **kwargs: Any) -> None:
        slug = kwargs.get("slug") or getattr(model, "__tablename__", model.__name__.lower())
        if slug in self._registry:
            raise RuntimeError(f"Slug '{slug}' already registered")
        ma = ModelAdmin(model=model, slug=slug, **{k: v for k, v in kwargs.items() if k != "slug"})
        self._registry[slug] = ma

    def get(self, slug: str) -> Optional[ModelAdmin]:
        return self._registry.get(slug)

    def all(self) -> List[ModelAdmin]:
        # упорядочим по slug для стабильности
        return [self._registry[k] for k in sorted(self._registry.keys())]


admin_site = AdminSite()

# --- Регистрация моделей ---

admin_site.register(
    User,
    slug="users",
    list_display=["id", "email", "username", "is_active"],
    form_fields=["email", "username", "is_active", "activation_key"],
    readonly_fields=["id"],
    field_labels={"email": "E-mail", "username": "Логин", "is_active": "Активен"},
    search_fields=["email", "username"],
    can_create=False,
    can_delete=False,
)

admin_site.register(
    Profile,
    slug="profiles",
    list_display=["id", "user_id", "nickname", "email", "verification"],
    form_fields=["nickname", "avatar", "first_name", "second_name", "phone", "email", "tg_id", "tg_nickname", "verification", "session"],
    readonly_fields=["id", "user_id", "avatar"],  # avatar меняем из профиля пользователя, здесь readonly
    field_labels={"verification": "Подтвержден"},
    search_fields=["nickname", "email", "tg_nickname", "phone"],
    can_create=False,
    can_delete=False,
)

admin_site.register(
    Permission,
    slug="permissions",
    list_display=["id", "profile_id", "is_superadmin", "is_admin", "is_staff", "is_updater", "is_reader", "is_user"],
    form_fields=["is_superadmin", "is_admin", "is_staff", "is_updater", "is_reader", "is_user"],
    readonly_fields=["id", "profile_id"],
    field_labels={
        "is_superadmin": "Суперпользователь",
        "is_admin": "Администратор",
        "is_staff": "Сотрудник",
        "is_updater": "Обновляющий",
        "is_reader": "Читатель",
        "is_user": "Пользователь",
    },
    search_fields=[],
    can_create=False,
    can_delete=False,
)
