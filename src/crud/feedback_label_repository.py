# path: src/crud/feedback_label_repository.py
from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.train.models.feedback_label import FeedbackLabel


class IFeedbackLabelRepository(Protocol):
    async def bulk_create_from_commit(
        self,
        session: AsyncSession,
        *,
        rows: list[dict[str, Any]],
        row_id_by_idx: dict[int, int],
        created_by: str,
        is_trusted: bool,
    ) -> int: ...


class FeedbackLabelRepository(IFeedbackLabelRepository):
    @staticmethod
    def _to_int_or_none(v: Any) -> int | None:
        try:
            if v is None:
                return None
            s = str(v).strip()
            if s == "":
                return None
            return int(s)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int_list(v: Any) -> list[int]:
        if not isinstance(v, list):
            return []
        out: list[int] = []
        for x in v:
            xi = FeedbackLabelRepository._to_int_or_none(x)
            if xi is not None:
                out.append(int(xi))
        return out

    async def bulk_create_from_commit(
        self,
        session: AsyncSession,
        *,
        rows: list[dict[str, Any]],
        row_id_by_idx: dict[int, int],
        created_by: str,
        is_trusted: bool,
    ) -> int:
        """
        rows[] ожидает поля (из normalize_commit_rows):
          - row_idx
          - label
          - selected_item_id
          - negatives
          - note

        Важно:
        - разные ревизии схемы могли называть колонки по-разному.
          Поэтому мы подстраиваемся под реальные колонки FeedbackLabel.
        """
        cols = set(FeedbackLabel.__table__.columns.keys())

        # куда писать выбранный item
        selected_key = None
        if "selected_item_id" in cols:
            selected_key = "selected_item_id"
        elif "selected_item" in cols:
            selected_key = "selected_item"

        # куда писать negatives
        negatives_key = None
        if "negatives" in cols:
            negatives_key = "negatives"
        elif "negative_item_ids" in cols:
            negatives_key = "negative_item_ids"
        elif "negatives_json" in cols:
            negatives_key = "negatives_json"

        objs: list[FeedbackLabel] = []

        for r in rows:
            if not isinstance(r, dict):
                continue

            row_idx = self._to_int_or_none(r.get("row_idx", 0)) or 0

            # row_idx может быть 0-based или 1-based — попробуем оба варианта
            row_id = row_id_by_idx.get(row_idx)
            if row_id is None:
                row_id = row_id_by_idx.get(row_idx + 1)
            if row_id is None:
                continue

            label = str(r.get("label", "") or "").strip() or "gold"
            selected_item_id = self._to_int_or_none(r.get("selected_item_id"))
            negatives = self._to_int_list(r.get("negatives", []))
            note = str(r.get("note", "") or "").strip() or None

            # если label=gold и ничего не выбрали — не падаем, помечаем ambiguous
            if label == "gold" and selected_item_id is None:
                label = "ambiguous"

            payload: dict[str, Any] = {}

            if "row_id" in cols:
                payload["row_id"] = int(row_id)

            if "label" in cols:
                payload["label"] = label

            if selected_key is not None:
                payload[selected_key] = int(selected_item_id) if selected_item_id is not None else None

            if negatives_key is not None:
                payload[negatives_key] = negatives

            if "note" in cols:
                payload["note"] = note

            if "created_by" in cols:
                payload["created_by"] = str(created_by)

            if "is_trusted" in cols:
                payload["is_trusted"] = bool(is_trusted)

            objs.append(FeedbackLabel(**payload))

        if not objs:
            return 0

        session.add_all(objs)
        await session.flush()
        return len(objs)
