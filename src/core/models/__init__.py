# src/core/models/__init__.py

__all__ = (
    "db_helper",
    "Base",
    "User",
    "Profile",
    "Permission",
    # не обязательно, но можно:
    "Item",
    "FeedbackSession",
    "FeedbackRow",
    "FeedbackCandidate",
    "FeedbackLabelModel",
    "TrainingRun",
    "TrainingRunRow",
)

from .db_helper import db_helper
from .base import Base
from .user import User
from .profile import Profile
from .permission import Permission

# ВАЖНО: импортируем модели других модулей, чтобы Alembic autogenerate видел их в Base.metadata
from src.fsnb_matcher.models import Item  # noqa: F401

from src.train.models import (  # noqa: F401
    FeedbackSession,
    FeedbackRow,
    FeedbackCandidate,
    FeedbackLabelModel,
    TrainingRun,
    TrainingRunRow,
)
