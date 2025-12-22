# path: src/scripts/init_vector_db.py
"""
Индексация Postgres → Qdrant (создание коллекции и заливка векторов).

Использование:
  docker compose exec app bash -lc "python -m src.scripts.init_vector_db"
"""

from __future__ import annotations

import asyncio

from src.app_logging import get_logger
from src.fsnb_matcher.services.index_qdrant import init_all_collections_entrypoint


logger = get_logger(__name__)


async def main() -> None:
    logger.info("init_vector_db_start")
    count = await init_all_collections_entrypoint()
    logger.info("init_vector_db_done", extra={"count": int(count)})


if __name__ == "__main__":
    asyncio.run(main())
