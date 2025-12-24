# path: src/crud/feedback_candidate_repository.py
from __future__ import annotations

from typing import Any, Protocol, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.train.models.feedback_candidate import FeedbackCandidate


class IFeedbackCandidateRepository(Protocol):
    async def bulk_create_from_topk(
        self,
        *,
        session: AsyncSession,
        topk: list[list[Any]],
        row_id_by_idx: dict[int, int],
        model_name: str,
        model_version: str | None = None,
    ) -> int: ...


class FeedbackCandidateRepository(IFeedbackCandidateRepository):
    @staticmethod
    def _safe_int(v: Any) -> int | None:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(v: Any) -> float | None:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    async def bulk_create_from_topk(
        self,
        *,
        session: AsyncSession,
        topk: list[list[Any]],
        row_id_by_idx: dict[int, int],
        model_name: str,
        model_version: str | None = None,
    ) -> int:
        """
        Создаёт записи feedback_candidates из top-K.

        Важно:
        - В разных ревизиях схемы поле модели могло называться `model` или `model_name`.
          Поэтому мы подставляем корректный ключ динамически по колонкам модели.
        """
        cols = set(FeedbackCandidate.__table__.columns.keys())

        # определяем, куда писать имя модели
        model_key = None
        if "model_name" in cols:
            model_key = "model_name"
        elif "model" in cols:
            model_key = "model"

        objs: list[FeedbackCandidate] = []

        for row_idx, cands in enumerate(topk):
            if not cands:
                continue

            # row_idx может быть 0-based или 1-based — пробуем оба варианта
            row_id = row_id_by_idx.get(row_idx)
            if row_id is None:
                row_id = row_id_by_idx.get(row_idx + 1)
            if row_id is None:
                continue

            for rank, cand in enumerate(cands, start=1):
                # cand может быть dict или объект
                if isinstance(cand, dict):
                    item_id = self._safe_int(cand.get("item_id") or cand.get("id"))
                    score = self._safe_float(cand.get("score"))
                else:
                    item_id = self._safe_int(getattr(cand, "item_id", None) or getattr(cand, "id", None))
                    score = self._safe_float(getattr(cand, "score", None))

                if item_id is None:
                    continue

                payload: dict[str, Any] = {}

                if "row_id" in cols:
                    payload["row_id"] = int(row_id)
                if "item_id" in cols:
                    payload["item_id"] = int(item_id)

                if "score" in cols:
                    payload["score"] = score

                if "rank" in cols:
                    payload["rank"] = int(rank)

                if "shown" in cols:
                    payload["shown"] = True

                if model_key is not None:
                    payload[model_key] = str(model_name)

                if "model_version" in cols:
                    payload["model_version"] = model_version

                objs.append(FeedbackCandidate(**payload))

        if not objs:
            return 0

        session.add_all(objs)
        await session.flush()
        return len(objs)
