# path: src/crud/feedback_row_repository.py
from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.train.models.feedback_row import FeedbackRow


class IFeedbackRowRepository(Protocol):
    async def bulk_create(
        self,
        *,
        session: AsyncSession,
        session_id: int,
        rows: list[dict[str, Any]],
    ) -> list[FeedbackRow]:
        raise NotImplementedError


class FeedbackRowRepository:
    """
    Репозиторий для feedback_rows.

    Важно:
    - payload из UI содержит служебные поля (row_idx, label, selected_item_id, negatives, note),
      которые НЕ обязаны существовать в модели FeedbackRow.
    - поэтому перед созданием FeedbackRow(...) нужно фильтровать kwargs
      по реальным колонкам таблицы, иначе будет:
        TypeError: '<field>' is an invalid keyword argument for FeedbackRow
    """

    @staticmethod
    def _filter_to_model_columns(data: dict[str, Any]) -> dict[str, Any]:
        """
        Оставляем только те ключи, которые реально являются колонками FeedbackRow.
        """
        cols = set(FeedbackRow.__table__.columns.keys())
        return {k: v for k, v in data.items() if k in cols}

    async def bulk_create(
        self,
        *,
        session: AsyncSession,
        session_id: int,
        rows: list[dict[str, Any]],
    ) -> list[FeedbackRow]:
        objs: list[FeedbackRow] = []

        for r in rows:
            if not isinstance(r, dict):
                continue

            # 1) Берём только разрешённые поля модели
            payload: dict[str, Any] = self._filter_to_model_columns(dict(r))

            # 2) session_id ставим всегда (если колонка есть)
            if "session_id" in FeedbackRow.__table__.columns.keys():
                payload["session_id"] = int(session_id)

            # 3) Алиасы из UI -> DB (если в модели есть такие поля)
            # UI обычно шлёт: units, qty
            # DB у тебя, судя по модели, хранит: units_in, qty_in
            cols = set(FeedbackRow.__table__.columns.keys())

            if "units_in" in cols and "units_in" not in payload:
                units_val = r.get("units_in", None)
                if units_val is None:
                    units_val = r.get("units", None)
                payload["units_in"] = units_val

            if "qty_in" in cols and "qty_in" not in payload:
                qty_val = r.get("qty_in", None)
                if qty_val is None:
                    qty_val = r.get("qty", None)
                payload["qty_in"] = qty_val

            # 4) created_by / is_trusted — если есть в модели, пробуем заполнить
            # (persist_commit передаёт это через actor_email/is_trusted в labels,
            # но для rows у тебя может быть нужно тоже)
            if "created_by" in cols and "created_by" not in payload:
                payload["created_by"] = r.get("created_by")  # может быть None — ок

            if "is_trusted" in cols and "is_trusted" not in payload:
                payload["is_trusted"] = bool(r.get("is_trusted", False))

            # 5) КРИТИЧНО: если в модели нет row_idx, мы его НЕ передаём.
            # (это и вызывает твою текущую ошибку)
            if "row_idx" not in cols and "row_idx" in payload:
                payload.pop("row_idx", None)

            objs.append(FeedbackRow(**payload))

        if not objs:
            return []

        session.add_all(objs)
        await session.flush()  # получаем id
        return objs
