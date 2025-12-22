# path: src/fsnb_matcher/services/matcher_service.py
"""
Сервис сопоставления элементов из JSON с базой ФСНБ.

DI-правило:
- Этот файл НЕ создаёт AsyncSession сам и НЕ делает SQLAlchemy-запросов напрямую.
- Вся работа с Postgres — через репозиторий из src/crud/.
- AsyncSession и репозиторий приходят снаружи (через Depends или через CLI-обвязку).

Производительность:
- Embeddings и Qdrant client синхронные → используем asyncio.to_thread.
- Метаданные из Postgres читаем батчем (без N+1).
"""

from __future__ import annotations

import asyncio
import io
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import Workbook
from qdrant_client.http import models as qmodels
from sqlalchemy.ext.asyncio import AsyncSession

from src.app_logging import get_logger
from src.core.config import settings
from src.crud.item_repository import IItemRepository
from src.fsnb_matcher.embeddings.model_giga import embed_texts
from src.fsnb_matcher.services.qdr import get_qdrant_client


logger = get_logger(__name__)

DEFAULT_COLLECTION_GIGA = "fsnb_giga"


def _safe_int(value: Any) -> Optional[int]:
    """Пытается привести value к int, иначе возвращает None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_collection_name() -> str:
    """
    Имя коллекции берём из settings.fsnb.qdrant_collection, если оно будет добавлено.
    Пока оставляем fallback на DEFAULT_COLLECTION_GIGA.
    """
    name = getattr(settings.fsnb, "qdrant_collection", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return DEFAULT_COLLECTION_GIGA


async def _embed_captions(captions: List[str]) -> List[List[float]]:
    """Эмбеддинги в отдельном потоке (не блокируем event loop)."""
    return await asyncio.to_thread(embed_texts, captions)


async def _qdrant_search(
    *,
    collection_name: str,
    vectors: list[list[float]],
    top_k: int,
) -> list[list[Any]]:
    """
    Qdrant batch search для qdrant-client==1.16.2.
    Возвращает список результатов (points) на каждый входной вектор.
    """
    client = get_qdrant_client()
    batch_size = 64

    def _sync_query() -> list[list[Any]]:
        all_results: list[list[Any]] = []

        for start in range(0, len(vectors), batch_size):
            chunk = vectors[start:start + batch_size]

            requests: list[qmodels.QueryRequest] = [
                qmodels.QueryRequest(
                    query=vec,
                    limit=int(top_k),
                    with_payload=True,
                    with_vector=False,
                )
                for vec in chunk
            ]

            responses: list[qmodels.QueryResponse] = client.query_batch_points(
                collection_name=collection_name,
                requests=requests,
            )

            all_results.extend([r.points or [] for r in responses])

        return all_results

    return await asyncio.to_thread(_sync_query)


async def match_items(
    session: AsyncSession,
    item_repo: IItemRepository,
    json_items: List[Dict[str, Any]],
    *,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Сопоставляет элементы JSON с коллекцией Qdrant.

    Вход:
        [{"Caption": "...", "Units": "...", "Quantity": "...", ...}, ...]
    Выход:
        добавляет поля:
        - "FSNB Name"
        - "FSNB code"
        - "FSNB Units"
        - "conf"
    """
    if not json_items:
        return []

    collection_name = _get_collection_name()
    captions = [str(i.get("Caption", "") or "") for i in json_items]

    logger.info(
        "Starting match",
        extra={"items": len(json_items), "top_k": int(top_k), "collection": collection_name},
    )

    vectors = await _embed_captions(captions)
    searches = await _qdrant_search(collection_name=collection_name, vectors=vectors, top_k=top_k)

    # 1) Собираем лучшие item_id и scores по каждой строке
    best_ids: List[Optional[int]] = []
    best_scores: List[float] = []

    for found in searches:
        if not found:
            best_ids.append(None)
            best_scores.append(0.0)
            continue

        best = found[0]
        best_scores.append(float(getattr(best, "score", 0.0)))
        best_ids.append(_safe_int(getattr(best, "id", None)))

    # 2) Батчем забираем метаданные из Postgres через репозиторий (без N+1)
    ids_to_fetch = [i for i in best_ids if i is not None]
    meta_map = await item_repo.fetch_items_meta_by_ids(session, ids_to_fetch)

    # 3) Формируем результат
    results: List[Dict[str, Any]] = []

    for idx, src in enumerate(json_items):
        item_id = best_ids[idx]
        score = best_scores[idx]

        if item_id is None or item_id not in meta_map:
            results.append(
                {
                    **src,
                    "FSNB Name": None,
                    "FSNB code": None,
                    "FSNB Units": None,
                    "conf": score,
                }
            )
            continue

        name, unit, code = meta_map[item_id]
        results.append(
            {
                **src,
                "FSNB Name": name,
                "FSNB code": code,
                "FSNB Units": unit,
                "conf": score,
            }
        )

    logger.info("Match completed", extra={"rows": len(results)})
    return results


async def build_match_xlsx(
    session: AsyncSession,
    item_repo: IItemRepository,
    payload: Dict[str, Any],
    *,
    top_k: int = 3,
) -> bytes:
    """
    Строит xlsx и возвращает bytes.

    Важно:
    - DI: session и item_repo передаются извне (роутером/скриптом).
    """
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = []

    matched = await match_items(session, item_repo, items, top_k=top_k)

    wb = Workbook()
    ws = wb.active
    ws.title = "GIGA"

    headers = [
        "Caption",
        "FSNB Name",
        "FSNB code",
        "Units",
        "FSNB Units",
        "Quantity",
        "conf",
    ]
    ws.append(headers)

    for row in matched:
        ws.append(
            [
                row.get("Caption", ""),
                row.get("FSNB Name"),
                row.get("FSNB code"),
                row.get("Units"),
                row.get("FSNB Units"),
                row.get("Quantity"),
                row.get("conf", 0.0),
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
