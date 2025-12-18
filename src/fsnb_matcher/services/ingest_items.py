# path: src/fsnb_matcher/services/ingest_items.py
"""
CLI-утилита: парсит все XML-файлы ФСНБ и вставляет их в таблицу items.
"""

from __future__ import annotations

import asyncio
from src.app_logging import get_logger
from src.fsnb_matcher.services.ingest import ingest_to_postgres

logger = get_logger(__name__)


async def main() -> None:
    logger.info("🚀 [ingest_items] Начинаем загрузку ФСНБ XML...")
    count = await ingest_to_postgres()
    logger.info(f"✅ [ingest_items] Завершено. Добавлено {count} строк.")


if __name__ == "__main__":
    asyncio.run(main())
