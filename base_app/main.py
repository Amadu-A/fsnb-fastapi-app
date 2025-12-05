# /base_app/main.py
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

# ВАЖНО: относительные импорты внутри пакета base_app
from .core.config import settings
from .core.models import db_helper
from .api import router as api_router
from .views import router as views_router  # HTML-вьюхи (/, /users/)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
    await db_helper.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # /static -> ./static (в корне проекта)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # HTML-views и API
    app.include_router(views_router)
    app.include_router(api_router, prefix=settings.api.prefix)
    return app


# Экспортируемый объект приложения
main_app = create_app()


if __name__ == "__main__":
    # Запуск: poetry run uvicorn base_app.main:main_app --reload
    uvicorn.run(
        "base_app.main:main_app",
        host=settings.run.host,
        port=settings.run.port,
        reload=True,
    )
