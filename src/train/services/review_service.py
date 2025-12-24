# path: src/train/services/review_service.py
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from src.app_logging import get_logger
from src.crud.item_repository import IItemRepository
from src.fsnb_matcher.services.matcher_service import _qdrant_search, _embed_captions, _get_collection_name, _safe_int


log = get_logger("train.review_service")


class ReviewService:
    """
    Сервис “подготовки данных для ревью”.

    Важно:
    - Не пишет в БД.
    - Даёт top-K кандидатов и структуру строк для Jinja/JS.
    """

    def __init__(self, item_repo: IItemRepository) -> None:
        self._item_repo = item_repo

    async def get_topk_for_captions(
        self,
        *,
        session,
        captions: List[str],
        top_k: int,
    ) -> list[list[dict[str, Any]]]:
        """
        Возвращает top-K кандидатов на каждый caption:
        [[{id, score, rank, code, name, unit, type}, ...], ...]
        """
        captions_clean = [str(c or "") for c in captions]
        vectors = await _embed_captions(captions_clean)

        collection = _get_collection_name()
        searches = await _qdrant_search(collection_name=collection, vectors=vectors, top_k=int(top_k))

        # собираем все item_id (по всем строкам), чтобы одним батчем добрать meta
        all_ids: list[int] = []
        per_row_ids: list[list[Optional[int]]] = []

        for found in searches:
            row_ids: list[Optional[int]] = []
            for rank, point in enumerate(found, start=1):
                pid = _safe_int(getattr(point, "id", None))
                row_ids.append(pid)
                if pid is not None:
                    all_ids.append(int(pid))
            per_row_ids.append(row_ids)

        meta_map = await self._item_repo.fetch_items_meta_by_ids(session, list(dict.fromkeys(all_ids)))

        result: list[list[dict[str, Any]]] = []
        for row_idx, found in enumerate(searches):
            row_payload: list[dict[str, Any]] = []
            for rank, point in enumerate(found, start=1):
                pid = _safe_int(getattr(point, "id", None))
                score = float(getattr(point, "score", 0.0))

                code = None
                name = None
                unit = None
                itype = None

                if pid is not None and pid in meta_map:
                    name, unit, code = meta_map[pid]
                    # type нам тут не отдают meta_map — если нужно, добавим позднее.
                    # Сейчас достаточно code/name/unit.
                    itype = None

                row_payload.append(
                    {
                        "id": pid,
                        "score": score,
                        "rank": int(rank),
                        "code": code,
                        "name": name,
                        "unit": unit,
                        "type": itype,
                    }
                )
            result.append(row_payload)

        return result

    async def build_initial_view_rows(
        self,
        *,
        session,
        rows: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """
        Подготовка строк для Jinja.
        Каждая строка получает:
          - candidates: top-K
          - auto_selected_item_id: top1 id (если есть)
          - label: по умолчанию gold, а если кандидатов нет — none_match
        """
        captions = [str(r.get("caption", "") or "") for r in rows]
        topk = await self.get_topk_for_captions(session=session, captions=captions, top_k=int(top_k))

        view_rows: list[dict[str, Any]] = []
        for idx, r in enumerate(rows):
            candidates = topk[idx] if idx < len(topk) else []
            auto_id = candidates[0]["id"] if candidates and candidates[0].get("id") is not None else None
            auto_label = "gold" if auto_id is not None else "none_match"

            view_rows.append(
                {
                    "row_idx": idx,
                    "caption": r.get("caption", ""),
                    "units": r.get("units"),
                    "qty": r.get("qty"),
                    "candidates": candidates,
                    "auto_selected_item_id": auto_id,
                    "selected_item_id": auto_id,  # текущий выбор (в JS может меняться)
                    "label": auto_label,
                    "note": "",
                }
            )

        return view_rows

    def normalize_commit_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Валидация/нормализация payload из UI при commit.

        Важно:
        - row_idx оставляем в нормализованном payload (нужно для маппинга строк UI -> feedback_rows).
        - запись row_idx в БД НЕ обязана происходить через модель (может не быть такого поля).
          Поэтому на этапе persist_commit мы будем отдельно готовить rows_for_db без row_idx.
        """
        out: list[dict[str, Any]] = []

        def _to_int_or_none(v: Any) -> int | None:
            try:
                return int(v) if v is not None and str(v).strip() != "" else None
            except Exception:
                return None

        for idx, r in enumerate(rows):
            if not isinstance(r, dict):
                continue

            caption = str(r.get("caption", "") or "")
            units = r.get("units")
            qty = r.get("qty")
            label = str(r.get("label", "") or "").strip() or "gold"

            selected_item_id = _to_int_or_none(r.get("selected_item_id", None))
            auto_selected_item_id = _to_int_or_none(r.get("auto_selected_item_id", None))

            note = str(r.get("note", "") or "").strip() or None
            negatives = r.get("negatives", [])

            neg_ids: list[int] = []
            if isinstance(negatives, list):
                for n in negatives:
                    ni = _to_int_or_none(n)
                    if ni is not None:
                        neg_ids.append(int(ni))

            # row_idx берём из UI, если нет — используем idx.
            # Это нужно для стабильного соответствия строк при сохранении labels/candidates.
            row_idx = _to_int_or_none(r.get("row_idx", None))
            if row_idx is None:
                row_idx = idx

            out.append(
                {
                    "row_idx": int(row_idx),
                    "caption": caption,
                    "units": str(units) if units is not None and str(units).strip() != "" else None,
                    "qty": str(qty) if qty is not None and str(qty).strip() != "" else None,
                    "label": label,
                    "selected_item_id": selected_item_id,
                    "auto_selected_item_id": auto_selected_item_id,
                    "negatives": neg_ids,
                    "note": note,
                }
            )

        return out
