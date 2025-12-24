# src/train/api/api_v1/__init__.py
from __future__ import annotations

from fastapi import APIRouter
from .review import router as review_router

router = APIRouter()
router.include_router(review_router, prefix="/review", tags=["review"])
