# path: src/admin.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from sqlalchemy.orm import DeclarativeMeta

from src.core.models.user import User
from src.core.models.profile import Profile
from src.core.models.permission import Permission

from src.fsnb_matcher.models.item import Item

from src.train.models.feedback_session import FeedbackSession
from src.train.models.feedback_row import FeedbackRow
from src.train.models.feedback_candidate import FeedbackCandidate
from src.train.models.feedback_label import FeedbackLabel
from src.train.models.training_run import TrainingRun
from src.train.models.training_run_row import TrainingRunRow


@dataclass
class ModelAdmin:
    """
    Описание модели для админки.
    """
    model: Type[DeclarativeMeta]
    slug: str
    list_display: List[str] = field(default_factory=list)
    form_fields: List[str] = field(default_factory=list)
    readonly_fields: List[str] = field(default_factory=list)
    field_labels: Dict[str, str] = field(default_factory=dict)
    search_fields: List[str] = field(default_factory=list)

    can_create: bool = False
    can_delete: bool = False

    # NEW: для read-only таблиц (например items) и/или композитного PK
    can_edit: bool = True

    # NEW: базовый page size (везде 50)
    page_size: int = 50


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
    readonly_fields=["id", "user_id", "avatar"],
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

# --- FSNB items (ТОЛЬКО ПРОСМОТР) ---
admin_site.register(
    Item,
    slug="items",
    list_display=["id", "code", "name", "unit", "type"],
    form_fields=[],                 # нет редактирования
    readonly_fields=["id", "code", "name", "unit", "type"],
    field_labels={"code": "Код", "name": "Наименование", "unit": "Ед.", "type": "Тип"},
    search_fields=["code", "name", "unit", "type"],
    can_create=False,
    can_delete=False,
    can_edit=False,
)

# --- TRAIN models ---
admin_site.register(
    FeedbackSession,
    slug="feedback_sessions",
    list_display=["id", "source_name", "status", "created_by", "created_at"],
    form_fields=["source_name", "status", "created_by"],
    readonly_fields=["id", "created_at"],
    search_fields=["source_name", "status", "created_by"],
    can_create=False,
    can_delete=True,     # нужно "очистить таблицу"
)

admin_site.register(
    FeedbackRow,
    slug="feedback_rows",
    list_display=["id", "session_id", "caption", "units_in", "qty_in", "is_trusted", "created_by", "created_at"],
    form_fields=["session_id", "caption", "units_in", "qty_in", "is_trusted", "created_by"],
    readonly_fields=["id", "created_at"],
    search_fields=["caption", "units_in", "qty_in", "created_by"],
    can_create=False,
    can_delete=True,
)

admin_site.register(
    FeedbackCandidate,
    slug="feedback_candidates",
    list_display=["id", "row_id", "item_id", "model_name", "model_version", "score", "rank", "shown", "created_at"],
    form_fields=["row_id", "item_id", "model_name", "model_version", "score", "rank", "shown"],
    readonly_fields=["id", "created_at"],
    search_fields=["model_name", "model_version"],
    can_create=False,
    can_delete=True,
)

admin_site.register(
    FeedbackLabel,
    slug="feedback_labels",
    list_display=["id", "row_id", "label", "selected_item_id", "is_trusted", "created_by", "created_at"],
    form_fields=["row_id", "label", "selected_item_id", "negatives", "note", "is_trusted", "created_by"],
    readonly_fields=["id", "created_at"],
    search_fields=["label", "created_by", "note"],
    can_create=False,
    can_delete=True,
)

admin_site.register(
    TrainingRun,
    slug="training_runs",
    list_display=["id", "mode", "base_model", "status", "started_at", "finished_at", "created_by"],
    form_fields=["mode", "base_model", "data_spec", "artifacts_path", "metrics", "status", "log_path", "finished_at", "created_by"],
    readonly_fields=["id", "started_at"],
    search_fields=["mode", "base_model", "status", "created_by"],
    can_create=False,
    can_delete=True,
)

# TrainingRunRow — композитный PK -> делаем просмотр/очистка
admin_site.register(
    TrainingRunRow,
    slug="training_run_rows",
    list_display=["run_id", "row_id", "added_at"],
    form_fields=[],  # ✅ нет формы редактирования
    readonly_fields=["run_id", "row_id", "added_at"],
    field_labels={
        "run_id": "Training run",
        "row_id": "Feedback row",
        "added_at": "Added at",
    },
    search_fields=[],
    can_create=False,
    can_delete=False,
)
