# path: src/scripts/create_fsnb_pg.py
"""
Импорт XML ФСНБ в PostgreSQL.
Используется при первом запуске:
  docker compose exec app bash -lc "python -m src.scripts.create_fsnb_pg"
"""

from __future__ import annotations

import asyncio
from src.app_logging import get_logger
from src.fsnb_matcher.services.ingest import ingest_to_postgres

logger = get_logger(__name__)


async def main() -> None:
    """Асинхронная точка входа — импортирует ФСНБ в базу."""
    logger.info("⏳ [create_fsnb_pg] Начало импорта XML → Postgres ...")
    inserted = await ingest_to_postgres()
    logger.info(f"✅ Импорт завершён: добавлено {inserted} записей.")


if __name__ == "__main__":
    asyncio.run(main())
