# /src/core/api/api_v1/__init__.py
from fastapi import APIRouter

from src.core.config import settings
from .users import router as users_router
from .auth import router as auth_router
from src.fsnb_matcher.api.api_v1 import router as fsnb_router

router = APIRouter(prefix=settings.api.v1.prefix)

# /api/<v1>/users/...
router.include_router(
    users_router,
    prefix=settings.api.v1.users,
)

# /api/<v1>/auth/...
router.include_router(
    auth_router,
    prefix=settings.api.v1.auth,   # <- префикс берём из конфига
)

router.include_router(fsnb_router,  prefix="",       tags=["fsnb-match"])