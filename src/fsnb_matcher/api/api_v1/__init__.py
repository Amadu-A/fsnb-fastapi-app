# src/fsnb_matcher/api/api_v1/__init__.py
from __future__ import annotations
from fastapi import APIRouter
from .match import router as match_router

router = APIRouter()
router.include_router(match_router, prefix="/fsnb", tags=["fsnb-match"])
