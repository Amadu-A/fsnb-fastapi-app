# path: src/train/services/report_service.py
from __future__ import annotations

import io
from typing import Any, Dict, List

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.item_repository import IItemRepository


class ReportService:
    """
    Формирование Excel-отчёта (ВОР) из финального выбора пользователя.
    На текущем срезе — минимально: Caption + выбранная позиция ФСНБ (code/name/unit) + Units/Qty.
    """

    def __init__(self, item_repo: IItemRepository) -> None:
        self._item_repo = item_repo

    async def build_result_xlsx(self, *, session: AsyncSession, rows: list[dict[str, Any]]) -> bytes:
        selected_ids: list[int] = []
        for r in rows:
            sid = r.get("selected_item_id")
            if isinstance(sid, int):
                selected_ids.append(int(sid))

        meta = await self._item_repo.fetch_items_meta_by_ids(session, list(dict.fromkeys(selected_ids)))

        wb = Workbook()
        ws = wb.active
        ws.title = "VOR"

        headers = [
            "Caption",
            "FSNB Name",
            "FSNB code",
            "Units",
            "FSNB Units",
            "Quantity",
            "Label",
        ]
        ws.append(headers)

        for r in rows:
            caption = r.get("caption", "")
            units = r.get("units")
            qty = r.get("qty")
            label = r.get("label", "")

            sid = r.get("selected_item_id")
            if isinstance(sid, int) and sid in meta:
                name, fsnb_unit, code = meta[sid]
            else:
                name, fsnb_unit, code = None, None, None

            ws.append([caption, name, code, units, fsnb_unit, qty, label])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
