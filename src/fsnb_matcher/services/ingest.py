# path: src/fsnb_matcher/services/ingest.py
from __future__ import annotations

from pathlib import Path

from src.core.config import settings
from src.core.models.db_helper import db_helper
from src.crud.item_repository import ItemRepository
from src.fsnb_matcher.services.fsnb_xml_parser import iter_items_from_fsnb_xml


async def ingest_to_postgres() -> int:
    fsnb_dir = Path(getattr(settings, "fsnb_dir", "/app/FSNB-2022_28_08_25"))
    inserted_total = 0

    async for session in db_helper.session_getter():
        rows = iter_items_from_fsnb_xml(fsnb_dir)
        inserted_total = await ItemRepository.bulk_insert_items(session, rows, chunk_size=1000)

    return inserted_total
