# /src/core/views/__init__.py
from fastapi import APIRouter
from .web import router as web_router
from .auth import router as auth_router
from .admin import router as admin_router

from src.train.views.review import router as train_review_router

# Единая точка подключения HTML-вьюх
router = APIRouter()
router.include_router(web_router)
router.include_router(auth_router)
router.include_router(admin_router)
router.include_router(train_review_router, prefix="/train")
