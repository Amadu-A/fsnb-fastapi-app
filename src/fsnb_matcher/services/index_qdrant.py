# path: src/fsnb_matcher/services/index_qdrant.py
from __future__ import annotations

import asyncio
from typing import List

from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy.ext.asyncio import AsyncSession

from src.app_logging import get_logger
from src.core.config import settings
from src.core.models.db_helper import db_helper
from src.crud.item_repository import IItemRepository, ItemRepository
from src.fsnb_matcher.embeddings import model_giga
from src.fsnb_matcher.services.qdr import get_qdrant_client


logger = get_logger(__name__)


def _get_collection_name() -> str:
    """
    Единый источник имени коллекции.
    Должно совпадать с matcher_service.
    """
    name = getattr(settings.fsnb, "qdrant_collection", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return "fsnb_giga"


async def init_all_collections(
    session: AsyncSession,
    item_repo: IItemRepository,
) -> int:
    """
    Создаёт коллекцию в Qdrant и заливает туда эмбеддинги (Giga) для всех items из Postgres.
    Возвращает количество залитых точек.

    Важно:
    - Postgres читаем потоково через item_repo.iter_for_index(), чтобы не держать всё в памяти.
    - encode()/upsert() синхронные → выносим в asyncio.to_thread.
    """
    client = get_qdrant_client()
    collection_name = _get_collection_name()

    dim = int(model_giga.dim())
    batch_size = int(settings.fsnb.giga_index_bs)

    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    logger.info("qdrant_collection_recreated", extra={"collection": collection_name, "dim": dim})

    done = 0
    ids_batch: List[int] = []
    texts_batch: List[str] = []

    async for item_id, name, _code, _unit, _type in item_repo.iter_for_index(session, yield_per=2000):
        ids_batch.append(int(item_id))
        texts_batch.append(str(name))

        if len(ids_batch) < batch_size:
            continue

        vectors = await asyncio.to_thread(model_giga.encode, texts_batch, False, len(texts_batch))
        if hasattr(vectors, "tolist"):
            vectors = vectors.tolist()

        points = [
            PointStruct(id=int(pid), vector=vec, payload={"name": texts_batch[idx]})
            for idx, (pid, vec) in enumerate(zip(ids_batch, vectors))
        ]

        await asyncio.to_thread(client.upsert, collection_name, points, False)
        done += len(points)

        if done % 1000 < batch_size:
            logger.info("qdrant_upsert_progress", extra={"done": done})

        ids_batch.clear()
        texts_batch.clear()

    # добиваем хвост
    if ids_batch:
        vectors = await asyncio.to_thread(model_giga.encode, texts_batch, False, len(texts_batch))
        if hasattr(vectors, "tolist"):
            vectors = vectors.tolist()

        points = [
            PointStruct(id=int(pid), vector=vec, payload={"name": texts_batch[idx]})
            for idx, (pid, vec) in enumerate(zip(ids_batch, vectors))
        ]
        await asyncio.to_thread(client.upsert, collection_name, points, False)
        done += len(points)

    logger.info("qdrant_upsert_done", extra={"collection": collection_name, "count": done})
    return done


async def init_all_collections_entrypoint() -> int:
    """
    Точка входа для CLI.
    Здесь допустимо создать session/repo (это обвязка).
    """
    item_repo: IItemRepository = ItemRepository()

    async with db_helper.session_factory() as session:
        return await init_all_collections(session, item_repo)
