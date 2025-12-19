# path: src/fsnb_matcher/services/qdr.py
"""
Утилиты для подключения и работы с Qdrant.
Используется индексатором и matcher_service.

DI/архитектура:
- Клиент Qdrant создаём один раз (singleton), чтобы не плодить подключения.
- Настройки берём из src/core/config.py -> settings.qdrant.
"""

from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient

from src.app_logging import get_logger
from src.core.config import settings


logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """
    Singleton QdrantClient.

    Почему singleton:
    - клиент создаётся тяжеловато (инициализация транспорта/проверки);
    - matcher_service и индексатор вызывают его много раз;
    - один экземпляр уменьшает накладные расходы и память.
    """
    host = settings.qdrant.host
    port = int(settings.qdrant.port)
    timeout = int(settings.qdrant.timeout_s)

    logger.info(
        "qdrant_client_create",
        extra={"host": host, "port": port, "timeout_s": timeout, "prefer_grpc": False},
    )

    return QdrantClient(
        host=host,
        port=port,
        prefer_grpc=False,
        timeout=timeout,
        check_compatibility=False,
    )
