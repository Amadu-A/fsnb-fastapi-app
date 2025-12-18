from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.fsnb_matcher.models.item import Item


RowTuple = Tuple[str, str, Optional[str], str]  # (code, name, unit, type)


class ItemRepository:
    """
    Репозиторий для таблицы items.

    ВАЖНО:
    - Старые функции (bulk_insert_items, fetch_*) интегрированы как методы класса
      и дополнительно оставлены как алиасы-методы, чтобы не ломать существующие вызовы.
    """

    # -----------------------------
    # НОВЫЕ базовые методы (удобно для CLI/сервисов)
    # -----------------------------
    @staticmethod
    async def truncate(session: AsyncSession) -> None:
        """Быстрый сброс таблицы + sequence."""
        await session.execute(text("TRUNCATE TABLE items RESTART IDENTITY;"))
        await session.commit()

    @staticmethod
    async def delete_all(session: AsyncSession) -> int:
        """Мягкая очистка (DELETE), если TRUNCATE не подходит."""
        res = await session.execute(delete(Item))
        await session.commit()
        return int(res.rowcount or 0)

    @staticmethod
    async def count(session: AsyncSession) -> int:
        res = await session.execute(text("SELECT COUNT(*) FROM items;"))
        return int(res.scalar_one())

    @staticmethod
    async def iter_for_index(
        session: AsyncSession,
        *,
        yield_per: int = 2000,
    ) -> AsyncIterator[Tuple[int, str, Optional[str], Optional[str], str]]:
        """
        Потоковая выгрузка для индексации:
        (id, name, code, unit, type)

        execution_options(yield_per=...) работает корректно вместе с session.stream(...)
        """
        stmt = (
            select(Item.id, Item.name, Item.code, Item.unit, Item.type)
            .order_by(Item.id)
            .execution_options(yield_per=yield_per)
        )

        stream = await session.stream(stmt)
        async for row in stream:
            yield (
                int(row[0]),
                str(row[1]),
                row[2] if row[2] is not None else None,
                row[3] if row[3] is not None else None,
                str(row[4]),
            )

    # -----------------------------
    # НОВОЕ bulk API (для сервисов)
    # -----------------------------
    @staticmethod
    async def bulk_upsert_dicts(
        session: AsyncSession,
        rows: Sequence[Dict[str, Any]],
    ) -> int:
        """
        rows: [{"code": "...", "name": "...", "unit": "...", "type": "work"}, ...]
        ON CONFLICT(code) DO NOTHING.

        Возвращает число обработанных строк как приближение (как и раньше),
        потому что rowcount на DO NOTHING бывает нестабилен.
        """
        if not rows:
            return 0

        stmt = (
            pg_insert(Item)
            .values(list(rows))
            .on_conflict_do_nothing(index_elements=[Item.code])
        )
        await session.execute(stmt)
        await session.commit()
        return len(rows)

    # -----------------------------
    # ✅ ИНТЕГРАЦИЯ СТАРОГО КОДА (bulk_insert_items + _flush)
    # -----------------------------
    @classmethod
    async def bulk_insert_items(
        cls,
        session: AsyncSession,
        rows: Iterable[RowTuple],
        chunk_size: int = 1000,
    ) -> int:
        """
        СТАРОЕ ПОВЕДЕНИЕ (интегрировано):

        Вставка (code, name, unit, type) с ON CONFLICT (code) DO NOTHING.
        Возвращает кол-во добавленных строк (приближенно) — как раньше.

        ВАЖНО:
        - Мы не пытаемся "точно" посчитать вставки по rowcount, потому что
          на on_conflict_do_nothing это реально может быть None/нестабильно.
        """
        buf: List[RowTuple] = []
        inserted = 0

        for row in rows:
            buf.append(row)
            if len(buf) >= chunk_size:
                inserted += await cls._flush(session, buf)
                buf.clear()

        if buf:
            inserted += await cls._flush(session, buf)

        return inserted

    @staticmethod
    async def _flush(session: AsyncSession, rows: List[RowTuple]) -> int:
        """
        СТАРЫЙ _flush (интегрирован):
        - commit делаем здесь, чтобы chunk-и фиксировались сразу.
        """
        stmt = (
            pg_insert(Item)
            .values([{"code": c, "name": n, "unit": u, "type": t} for (c, n, u, t) in rows])
            .on_conflict_do_nothing(index_elements=[Item.code])
        )
        await session.execute(stmt)
        await session.commit()
        # rowcount может быть None -> возвращаем len(rows) как приближение (как было)
        return len(rows)

    # -----------------------------
    # ✅ ИНТЕГРАЦИЯ СТАРЫХ fetch_* ФУНКЦИЙ
    # -----------------------------
    @staticmethod
    async def fetch_all_item_ids_and_names(session: AsyncSession) -> List[Tuple[int, str]]:
        res = await session.execute(select(Item.id, Item.name).order_by(Item.id))
        return [(int(i), str(n)) for (i, n) in res.all()]

    @staticmethod
    async def fetch_item_name_unit_by_id(
        session: AsyncSession,
        item_id: int,
    ) -> Optional[Tuple[str, Optional[str]]]:
        res = await session.execute(select(Item.name, Item.unit).where(Item.id == int(item_id)))
        row = res.first()
        return (str(row[0]), row[1]) if row else None

    @staticmethod
    async def fetch_item_name_unit_code_by_id(
        session: AsyncSession,
        item_id: int,
    ) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
        res = await session.execute(select(Item.name, Item.unit, Item.code).where(Item.id == int(item_id)))
        row = res.first()
        return (str(row[0]), row[1], row[2]) if row else None

    @staticmethod
    async def fetch_item_codes(
        session: AsyncSession,
        item_ids: Sequence[int],
    ) -> Dict[int, Optional[str]]:
        if not item_ids:
            return {}

        ids = sorted({int(i) for i in item_ids if i is not None})
        if not ids:
            return {}

        res = await session.execute(select(Item.id, Item.code).where(Item.id.in_(ids)))
        return {int(i): (c if c is not None else None) for (i, c) in res.all()}

    # -----------------------------
    # ✅ СОВМЕСТИМОСТЬ: алиасы (если где-то ожидали функциональный стиль)
    # -----------------------------
    # Если в коде раньше было: from src.crud.item_repository import bulk_insert_items
    # и ты хочешь не переписывать импорты — можно в конце файла оставить функции-обёртки.
    # Но ты просил "не сохранять старые функции" — поэтому алиасы оставляю только методами класса.
