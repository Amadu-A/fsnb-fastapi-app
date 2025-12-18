from __future__ import annotations

from typing import List, Tuple

from qdrant_client.models import Distance, VectorParams, PointStruct

from src.app_logging import get_logger
from src.core.config import settings
from src.core.models.db_helper import db_helper
from src.crud.item_repository import ItemRepository
from src.fsnb_matcher.services.qdr import get_qdrant_client
from src.fsnb_matcher.embeddings import model_giga  # <-- поправь импорт под свой путь

logger = get_logger(__name__)

COLLECTION_GIGA = "fsnb_giga"  # можешь вынести в settings позже


async def fetch_all_item_ids_and_names() -> List[Tuple[int, str]]:
    async for session in db_helper.session_getter():
        return await ItemRepository.fetch_all_item_ids_and_names(session)
    return []


async def init_all_collections() -> int:
    """
    Создаёт коллекцию в Qdrant и заливает туда эмбеддинги (Giga) для всех items из Postgres.
    Возвращает количество залитых точек.
    """
    items = await fetch_all_item_ids_and_names()
    total = len(items)
    logger.info({"event": "pg_items_loaded", "count": total})

    if total == 0:
        return 0

    client = get_qdrant_client()

    dim = int(model_giga.dim())
    batch = int(settings.fsnb.giga_index_bs)  # микро-батч для Giga, напр. 8

    # пересоздаём коллекцию
    client.recreate_collection(
        collection_name=COLLECTION_GIGA,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    logger.info({"event": "qdrant_collection_recreated", "collection": COLLECTION_GIGA, "dim": dim})

    done = 0
    for i in range(0, total, batch):
        chunk = items[i : i + batch]
        ids = [item_id for (item_id, _) in chunk]
        texts = [name for (_, name) in chunk]

        vectors = model_giga.encode(texts, is_query=False, batch_size=len(texts))

        points = [
            PointStruct(id=int(pid), vector=vec, payload={"name": texts[idx]})
            for idx, (pid, vec) in enumerate(zip(ids, vectors))
        ]

        client.upsert(collection_name=COLLECTION_GIGA, points=points, wait=False)
        done += len(points)

        if done % 1000 < batch:
            logger.info({"event": "qdrant_upsert_progress", "done": done, "total": total})

    logger.info({"event": "qdrant_upsert_done", "collection": COLLECTION_GIGA, "count": done})
    return done
