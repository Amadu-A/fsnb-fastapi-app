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

    Логика сохранена (как в вашей версии):
    - если передан session_id -> сохраняем метки в существующую draft-сессию и закрываем её
    - fallback (без session_id) оставлен для старых вызовов (но UI должен слать session_id)
    - commit идемпотентен: старые labels удаляются и заменяются новыми
    - candidates в NEW PATH не пересоздаются (они уже созданы при /create)
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
        Fallback path: готовим rows для bulk_create.
        (Оставляем caption/units/qty как у вас было)
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
                }
            )
        return out

    @staticmethod
    def _build_row_id_by_idx(
        *,
        db_rows: list[Any],
        commit_rows: list[dict[str, Any]],
    ) -> dict[int, int]:
        """
        Привязка commit row_idx -> DB row_id.

        В вашей схеме FeedbackRow не хранит row_idx, поэтому:
        - берём rows сессии в порядке id ASC
        - commit_rows сортируем по row_idx
        - считаем, что порядок совпадает
        """
        commit_rows_sorted = sorted(commit_rows, key=lambda r: int(r.get("row_idx", 0)))

        mapping: dict[int, int] = {}
        for i, db_row in enumerate(db_rows):
            if i >= len(commit_rows_sorted):
                break
            row_idx = int(commit_rows_sorted[i].get("row_idx", i))
            mapping[row_idx] = int(db_row.id)
        return mapping

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
        session_id: int | None = None,
    ) -> int:
        # ----------- NEW PATH: commit into existing draft session -----------
        if session_id is not None:
            fb_session = await self._session_repo.get(session=session, session_id=int(session_id))
            if not fb_session:
                raise ValueError(f"FeedbackSession {session_id} not found")

            if str(getattr(fb_session, "status", "") or "") == "closed":
                raise ValueError(f"FeedbackSession {session_id} already closed")

            # DB rows for that session (внутри repo)
            db_rows = await self._row_repo.list_by_session_id(session=session, session_id=int(session_id))
            if not db_rows:
                raise ValueError(f"FeedbackSession {session_id} has no rows")

            row_id_by_idx = self._build_row_id_by_idx(db_rows=db_rows, commit_rows=rows)

            # commit idempotent: delete existing labels for these rows
            row_ids = [int(r.id) for r in db_rows]
            await self._label_repo.delete_by_row_ids(session=session, row_ids=row_ids)

            # set trusted flag for all rows of this session (если такие поля есть)
            await self._row_repo.mark_session_rows_trusted(
                session=session,
                session_id=int(session_id),
                is_trusted=bool(is_trusted),
                created_by=str(actor_email),
            )

            # write labels
            await self._label_repo.bulk_create_from_commit(
                session=session,
                rows=rows,
                row_id_by_idx=row_id_by_idx,
                created_by=str(actor_email),
                is_trusted=bool(is_trusted),
            )

            # close same session (no duplicates)
            await self._session_repo.close(session=session, session_id=int(session_id))

            log.info(
                {
                    "event": "feedback_saved_existing_session",
                    "feedback_session_id": int(session_id),
                    "rows": len(rows),
                    "trusted": bool(is_trusted),
                }
            )
            return int(session_id)

        # ----------- OLD PATH: (fallback) creates new session -----------
        fb_session = await self._session_repo.create(
            session=session,
            source_name=source_name,
            created_by=str(actor_email),
        )

        rows_for_db = self._rows_for_db(rows)
        fb_rows = await self._row_repo.bulk_create(
            session=session,
            session_id=int(fb_session.id),
            rows=rows_for_db,
        )

        review_svc = ReviewService(item_repo=self._item_repo)
        captions = [str(r.get("caption", "") or "") for r in rows]
        topk = await review_svc.get_topk_for_captions(
            session=session,
            captions=captions,
            top_k=int(top_k),
        )

        row_id_by_idx: dict[int, int] = {}
        for i, r_model in enumerate(fb_rows):
            row_idx = int(rows[i].get("row_idx", i))
            row_id_by_idx[row_idx] = int(r_model.id)

        await self._candidate_repo.bulk_create_from_topk(
            session=session,
            topk=topk,
            row_id_by_idx=row_id_by_idx,
            model_name="giga",
        )

        await self._label_repo.bulk_create_from_commit(
            session=session,
            rows=rows,
            row_id_by_idx=row_id_by_idx,
            created_by=str(actor_email),
            is_trusted=bool(is_trusted),
        )

        await self._session_repo.close(session=session, session_id=int(fb_session.id))

        log.info(
            {
                "event": "feedback_saved_new_session_fallback",
                "feedback_session_id": int(fb_session.id),
                "rows": len(rows),
                "trusted": bool(is_trusted),
            }
        )
        return int(fb_session.id)
