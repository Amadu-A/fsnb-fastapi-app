# src/core/api/__init__.py
from fastapi import APIRouter

from .api_v1 import router as router_api_v1
from src.core.config import settings

router = APIRouter(
    prefix=settings.api.prefix
)
router.include_router(
    router_api_v1,
)
