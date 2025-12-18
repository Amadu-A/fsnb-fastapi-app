# path: src/fsnb_matcher/services/qdr.py
"""
Утилиты для подключения и работы с Qdrant.
Используется индексатором и matcher_service.
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from src.app_logging import get_logger
from src.core.config import settings

logger = get_logger(__name__)


def get_qdrant_client() -> QdrantClient:
    """
    Возвращает экземпляр клиента Qdrant, используя настройки из .env.
    """
    logger.info(f"🔗 Подключение к Qdrant: {settings.qdrant.host}:{settings.qdrant.port}")
    client = QdrantClient(
        host=settings.qdrant.host,
        port=settings.qdrant.port,
        prefer_grpc=False,
        timeout=settings.qdrant.timeout_s,
        check_compatibility=False,
    )
    return client
