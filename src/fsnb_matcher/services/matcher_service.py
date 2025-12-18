# path: src/fsnb_matcher/services/matcher_service.py
"""
Сервис сопоставления элементов из JSON с базой ФСНБ.

Совместимость:
- Роутер сейчас импортирует build_match_xlsx(), поэтому эта функция обязана существовать.
- Новая логика сопоставления реализована в match_items() и используется внутри build_match_xlsx().

Производительность:
- Embeddings и Qdrant client синхронные → выносим в asyncio.to_thread, чтобы не блокировать event loop.
- Работа с Postgres через AsyncSession (db_helper.session_factory()).
"""

from __future__ import annotations

import asyncio
import io
from typing import Any, Dict, List, Optional, Tuple
from qdrant_client.http import models as qmodels

from openpyxl import Workbook

from src.app_logging import get_logger
from src.core.config import settings
from src.core.models.db_helper import db_helper
from src.crud.item_repository import ItemRepository
from src.fsnb_matcher.embeddings.model_giga import embed_texts
from src.fsnb_matcher.services.qdr import get_qdrant_client

logger = get_logger(__name__)


def _safe_int(value: Any) -> Optional[int]:
    """Пытается привести value к int, иначе возвращает None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _embed_captions(captions: List[str]) -> List[List[float]]:
    """Эмбеддинги в отдельном потоке (не блокируем event loop)."""
    return await asyncio.to_thread(embed_texts, captions)


# async def _qdrant_search(
#     *,
#     collection_name: str,
#     vectors: List[List[float]],
#     top_k: int,
# ) -> List[List[Any]]:
#     """
#     Поиск в Qdrant для каждого вектора.
#     Возвращает список результатов на каждый caption.
#     """
#     client = get_qdrant_client()
#
#     def _do_search_one(vec: List[float]) -> List[Any]:
#
#         # return client.search(
#         #     collection_name=collection_name,
#         #     query_vector=vec,
#         #     limit=top_k,
#         # )
#         client.sea
#         res =  client.query_points(
#             collection_name=collection_name,
#             query=vec,  # query_vector в некоторых версиях называется query
#             limit=top_k,
#             with_payload=True,
#             with_vectors=False,
#         )
#         return list(getattr(res, "points", []) or [])
#
#     tasks = [asyncio.to_thread(_do_search_one, vec) for vec in vectors]
#     return await asyncio.gather(*tasks)


from qdrant_client import models as qmodels  # важно: именно так


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
            chunk = vectors[start : start + batch_size]

            # В 1.16.x используем QueryRequest(query=<vector>)
            requests: list[qmodels.QueryRequest] = [
                qmodels.QueryRequest(
                    query=vec,            # <-- ВЕКТОР ЗАПРОСА (а не FilterSelector)
                    limit=top_k,
                    with_payload=True,    # можно False, если payload не используешь
                    with_vector=False,    # <-- ВАЖНО: with_vector, не with_vectors
                )
                for vec in chunk
            ]

            # Возвращает list[QueryResponse], в каждом ответе лежит .points
            responses: list[qmodels.QueryResponse] = client.query_batch_points(
                collection_name=collection_name,
                requests=requests,
            )

            all_results.extend([r.points or [] for r in responses])

        return all_results

    return await asyncio.to_thread(_sync_query)






async def _fetch_meta_by_item_id(
    item_id: int,
) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """Достаёт (name, unit, code) из Postgres по item_id."""
    async with db_helper.session_factory() as session:
        return await ItemRepository.fetch_item_name_unit_code_by_id(session, item_id)


async def match_items(
    json_items: List[Dict[str, Any]],
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

    collection_name = getattr(getattr(settings, "fsnb", None), "qdrant_collection", None)
    if not isinstance(collection_name, str) or not collection_name.strip():
        collection_name = "fsnb_giga"

    captions = [str(i.get("Caption", "") or "") for i in json_items]

    logger.info(
        "Starting match",
        extra={"items": len(json_items), "top_k": top_k, "collection": collection_name},
    )

    vectors = await _embed_captions(captions)
    searches = await _qdrant_search(collection_name=collection_name, vectors=vectors, top_k=top_k)

    results: List[Dict[str, Any]] = []

    for idx, found in enumerate(searches):
        if not found:
            results.append(
                {
                    **json_items[idx],
                    "FSNB Name": None,
                    "FSNB code": None,
                    "FSNB Units": None,
                    "conf": 0.0,
                }
            )
            continue

        best = found[0]
        score = float(getattr(best, "score", 0.0))
        raw_id = getattr(best, "id", None)
        item_id = _safe_int(raw_id)

        if item_id is None:
            results.append(
                {
                    **json_items[idx],
                    "FSNB Name": None,
                    "FSNB code": None,
                    "FSNB Units": None,
                    "conf": score,
                }
            )
            continue

        meta = await _fetch_meta_by_item_id(item_id)
        if not meta:
            results.append(
                {
                    **json_items[idx],
                    "FSNB Name": None,
                    "FSNB code": None,
                    "FSNB Units": None,
                    "conf": score,
                }
            )
            continue

        name, unit, code = meta
        results.append(
            {
                **json_items[idx],
                "FSNB Name": name,
                "FSNB code": code,
                "FSNB Units": unit,
                "conf": score,
            }
        )

    logger.info("Match completed", extra={"rows": len(results)})
    return results


async def build_match_xlsx(
    payload: Dict[str, Any],
    *,
    top_k: int = 3,
) -> bytes:
    """
    Совместимый API для старого роутера:
    - принимает payload вида {"items":[{...}, {...}]}
    - строит xlsx и возвращает bytes.

    Это позволяет не менять src/fsnb_matcher/api/api_v1/match.py прямо сейчас.
    """
    items = payload.get("items", [])
    if not isinstance(items, list):
        items = []

    matched = await match_items(items, top_k=top_k)

    wb = Workbook()
    ws = wb.active
    ws.title = "GIGA"

    # Заголовки (как ты описывал)
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
