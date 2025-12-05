# /base_app/views/__init__.py
from fastapi import APIRouter
from .web import router as web_router

# Единая точка подключения HTML-вьюх
router = APIRouter()
router.include_router(web_router)
