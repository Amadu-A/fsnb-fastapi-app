# path: src/train/services/feedback_persist_service.py

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.app_logging import get_logger
from src.crud.item_repository import IItemRepository
from src.crud.feedback_session_repository import (
    IFeedbackSessionRepository,
    FeedbackSessionRepository,
)
from src.crud.feedback_row_repository import (
    IFeedbackRowRepository,
    FeedbackRowRepository,
)
from src.crud.feedback_candidate_repository import (
    IFeedbackCandidateRepository,
    FeedbackCandidateRepository,
)
from src.crud.feedback_label_repository import (
    IFeedbackLabelRepository,
    FeedbackLabelRepository,
)
from src.train.services.review_service import ReviewService


log = get_logger("train.feedback_persist")


class FeedbackPersistService:
    """
    Сохранение итогов ревью в feedback_*.

    Стратегия:
    - создаём feedback_session
    - создаём feedback_rows
    - считаем top-K заново (чтобы гарантированно сохранить “что показывали”)
    - сохраняем feedback_candidates
    - сохраняем feedback_labels (trusted/draft по роли)
    """

    def __init__(
        self,
        *,
        item_repo: IItemRepository,
        session_repo: IFeedbackSessionRepository | None = None,
        row_repo: IFeedbackRowRepository | None = None,
        candidate_repo: IFeedbackCandidateRepository | None = None,
        label_repo: IFeedbackLabelRepository | None = None,
    ) -> None:
        self._item_repo = item_repo
        self._session_repo = session_repo or FeedbackSessionRepository()
        self._row_repo = row_repo or FeedbackRowRepository()
        self._candidate_repo = candidate_repo or FeedbackCandidateRepository()
        self._label_repo = label_repo or FeedbackLabelRepository()

    @staticmethod
    def _rows_for_db(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Подготовка rows для вставки в feedback_rows.

        Почему нужно:
        - payload из UI/normalize_commit_rows содержит служебные поля (например row_idx),
          которые могут НЕ существовать в SQLAlchemy-модели FeedbackRow.
        - если передать их в FeedbackRow(**row) — получим:
          TypeError: '<field>' is an invalid keyword argument for FeedbackRow

        Поэтому для БД оставляем только то, что точно относится к строке:
        caption/units/qty (+ любые другие поля, которые реально есть в вашей модели).
        """
        out: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "caption": r.get("caption"),
                    "units": r.get("units"),
                    "qty": r.get("qty"),
                    # row_idx НЕ передаём в модель
                    # label/selected_item_id/negatives/note тоже НЕ являются полями FeedbackRow
                }
            )
        return out

    async def persist_commit(
        self,
        *,
        session: AsyncSession,
        source_name: str,
        actor_email: str,
        actor_user_id: int,
        is_trusted: bool,
        rows: list[dict[str, Any]],
        top_k: int = 5,
    ) -> int:
        # 1) создаём feedback_session
        fb_session = await self._session_repo.create(
            session=session,
            source_name=source_name,
            created_by=str(actor_email),
        )

        # 2) строки (в БД пишем только “чистые” поля, без row_idx/label/etc)
        rows_for_db = self._rows_for_db(rows)

        fb_rows = await self._row_repo.bulk_create(
            session=session,
            session_id=int(fb_session.id),
            rows=rows_for_db,
        )

        # 3) пересчёт top-K и сохранение кандидатов
        review_svc = ReviewService(item_repo=self._item_repo)
        captions = [str(r.get("caption", "") or "") for r in rows]
        topk = await review_svc.get_topk_for_captions(
            session=session,
            captions=captions,
            top_k=int(top_k),
        )

        # row_id привязываем к row_idx.
        # Важно: модель FeedbackRow может НЕ иметь поля row_idx.
        # Тогда мы используем порядок вставки: fb_rows[i] соответствует rows[i].
        row_id_by_idx: dict[int, int] = {}

        for i, r_model in enumerate(fb_rows):
            db_row_id = int(r_model.id)

            model_row_idx = getattr(r_model, "row_idx", None)
            if model_row_idx is not None:
                try:
                    row_idx = int(model_row_idx)
                except Exception:
                    row_idx = int(rows[i].get("row_idx", i))
            else:
                row_idx = int(rows[i].get("row_idx", i))

            row_id_by_idx[row_idx] = db_row_id

        await self._candidate_repo.bulk_create_from_topk(
            session=session,
            topk=topk,
            row_id_by_idx=row_id_by_idx,
            model_name="giga",
        )

        # 4) labels (используем исходные rows, где есть row_idx/label/selected_item_id/negatives/note)
        await self._label_repo.bulk_create_from_commit(
            session=session,
            rows=rows,
            row_id_by_idx=row_id_by_idx,
            created_by=str(actor_email),
            is_trusted=bool(is_trusted),
        )

        # 5) закрываем сессию
        await self._session_repo.close(session=session, session_id=int(fb_session.id))

        log.info(
            {
                "event": "feedback_saved",
                "feedback_session_id": int(fb_session.id),
                "rows": len(rows),
                "trusted": bool(is_trusted),
            }
        )
        return int(fb_session.id)
