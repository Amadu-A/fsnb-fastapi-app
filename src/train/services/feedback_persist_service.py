# path: src/train/services/feedback_persist_service.py
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update
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
from src.train.models.feedback_session import FeedbackSession
from src.train.models.feedback_row import FeedbackRow
from src.train.models.feedback_label import FeedbackLabel
from src.train.services.review_service import ReviewService

log = get_logger("train.feedback_persist")


class FeedbackPersistService:
    """
    Сохранение итогов ревью в feedback_*.

    Раньше persist_commit создавал НОВУЮ сессию и дублировал строки/кандидатов.
    Теперь:
    - если передан session_id -> сохраняем метки в существующую draft-сессию и закрываем её
    - fallback (без session_id) оставлен на случай старых вызовов, но UI должен всегда слать session_id
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
        db_rows: list[FeedbackRow],
        commit_rows: list[dict[str, Any]],
    ) -> dict[int, int]:
        """
        Привязка commit row_idx -> DB row_id.

        В вашей схеме FeedbackRow не хранит row_idx, поэтому делаем минимально:
        считаем, что порядок строк в UI соответствует порядку вставки в БД (id ASC).

        Если когда-то захотите сделать "железобетонно", добавьте FeedbackRow.row_idx
        и заполняйте при /create.
        """
        # commit_rows может прийти не отсортированным
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
            fb_session = await session.get(FeedbackSession, int(session_id))
            if not fb_session:
                raise ValueError(f"FeedbackSession {session_id} not found")

            if str(getattr(fb_session, "status", "") or "") == "closed":
                raise ValueError(f"FeedbackSession {session_id} already closed")

            # DB rows for that session
            db_rows = (
                (await session.execute(
                    select(FeedbackRow)
                    .where(FeedbackRow.session_id == int(session_id))
                    .order_by(FeedbackRow.id.asc())
                ))
                .scalars()
                .all()
            )
            if not db_rows:
                raise ValueError(f"FeedbackSession {session_id} has no rows")

            row_id_by_idx = self._build_row_id_by_idx(db_rows=db_rows, commit_rows=rows)

            # make commit idempotent: delete existing labels for these rows
            row_ids = [int(r.id) for r in db_rows]
            await session.execute(delete(FeedbackLabel).where(FeedbackLabel.row_id.in_(row_ids)))

            # set trusted flag for all rows of this session
            await session.execute(
                update(FeedbackRow)
                .where(FeedbackRow.session_id == int(session_id))
                .values(is_trusted=bool(is_trusted), created_by=str(actor_email))
            )

            # write labels (uses payload rows: row_idx/label/selected_item_id/negatives/note)
            await self._label_repo.bulk_create_from_commit(
                session=session,
                rows=rows,
                row_id_by_idx=row_id_by_idx,
                created_by=str(actor_email),
                is_trusted=bool(is_trusted),
            )

            # close same session (no duplicates)
            await session.execute(
                update(FeedbackSession)
                .where(FeedbackSession.id == int(session_id))
                .values(status="closed")
            )

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
        # Оставлено для совместимости, но UI должен всегда присылать session_id
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
