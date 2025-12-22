# path: src/fsnb_matcher/services/ingest.py
from __future__ import annotations

from pathlib import Path

from src.core.config import settings
from src.core.models.db_helper import db_helper
from src.crud.item_repository import IItemRepository, ItemRepository
from src.fsnb_matcher.services.fsnb_xml_parser import iter_items_from_fsnb_xml


async def ingest_to_postgres() -> int:
    """
    Импорт ФСНБ в Postgres.

    Правила, которые соблюдаем:
    - настройки берём из src/core/config.py (settings.fsnb.fsnb_dir)
    - сессию создаём через session_factory() (это НЕ FastAPI Depends-контекст)
    - БД операции только через репозиторий (src/crud/)
    """
    fsnb_dir = Path(settings.fsnb.fsnb_dir)
    inserted_total = 0

    item_repo: IItemRepository = ItemRepository()

    async with db_helper.session_factory() as session:
        rows = iter_items_from_fsnb_xml(fsnb_dir)
        inserted_total = await item_repo.bulk_insert_items(session, rows, chunk_size=1000)

    return inserted_total
