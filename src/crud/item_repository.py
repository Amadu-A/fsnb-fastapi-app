# path: src/crud/item_repository.py
from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

from sqlalchemy import delete, select, text, or_, case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.fsnb_matcher.models.item import Item


RowTuple = Tuple[str, str, Optional[str], str]  # (code, name, unit, type)


class IItemRepository(Protocol):
    """
    Интерфейс репозитория items (DI-контракт).

    Зачем:
    - единый паттерн: Protocol + реализация;
    - удобно мокать в тестах;
    - удобно указывать тип в Depends.
    """

    async def truncate(self, session: AsyncSession) -> None: ...
    async def delete_all(self, session: AsyncSession) -> int: ...
    async def count(self, session: AsyncSession) -> int: ...

    async def iter_for_index(
        self,
        session: AsyncSession,
        *,
        yield_per: int = 2000,
    ) -> AsyncIterator[Tuple[int, str, Optional[str], Optional[str], str]]: ...

    async def bulk_upsert_dicts(
        self,
        session: AsyncSession,
        rows: Sequence[Dict[str, Any]],
    ) -> int: ...

    async def bulk_insert_items(
        self,
        session: AsyncSession,
        rows: Iterable[RowTuple],
        chunk_size: int = 1000,
    ) -> int: ...

    async def fetch_all_item_ids_and_names(self, session: AsyncSession) -> List[Tuple[int, str]]: ...

    async def fetch_item_name_unit_by_id(
        self,
        session: AsyncSession,
        item_id: int,
    ) -> Optional[Tuple[str, Optional[str]]]: ...

    async def fetch_item_name_unit_code_by_id(
        self,
        session: AsyncSession,
        item_id: int,
    ) -> Optional[Tuple[str, Optional[str], Optional[str]]]: ...

    async def fetch_item_codes(
        self,
        session: AsyncSession,
        item_ids: Sequence[int],
    ) -> Dict[int, Optional[str]]: ...

    async def fetch_items_meta_by_ids(
        self,
        session: AsyncSession,
        item_ids: Sequence[int],
    ) -> Dict[int, Tuple[str, Optional[str], Optional[str]]]: ...

    async def search_items(
        self,
        session: AsyncSession,
        *,
        query: str,
        limit: int = 20,
    ) -> List[Item]: ...

class ItemRepository(IItemRepository):
    """
    Репозиторий для таблицы items.

    Правило:
    - SQL/DB вызовы живут только здесь (src/crud/).
    """

    async def truncate(self, session: AsyncSession) -> None:
        """TRUNCATE + reset identity."""
        await session.execute(text("TRUNCATE TABLE items RESTART IDENTITY;"))
        await session.commit()

    async def delete_all(self, session: AsyncSession) -> int:
        """DELETE всех строк (если TRUNCATE не подходит)."""
        res = await session.execute(delete(Item))
        await session.commit()
        return int(res.rowcount or 0)

    async def count(self, session: AsyncSession) -> int:
        """COUNT(*) по items."""
        res = await session.execute(text("SELECT COUNT(*) FROM items;"))
        return int(res.scalar_one())

    async def iter_for_index(
        self,
        session: AsyncSession,
        *,
        yield_per: int = 2000,
    ) -> AsyncIterator[Tuple[int, str, Optional[str], Optional[str], str]]:
        """Потоковая выгрузка (id, name, code, unit, type) для индексации."""
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

    async def bulk_upsert_dicts(
        self,
        session: AsyncSession,
        rows: Sequence[Dict[str, Any]],
    ) -> int:
        """Bulk insert dicts с ON CONFLICT(code) DO NOTHING."""
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

    async def bulk_insert_items(
        self,
        session: AsyncSession,
        rows: Iterable[RowTuple],
        chunk_size: int = 1000,
    ) -> int:
        """Вставка кортежей (code,name,unit,type) чанками."""
        buf: List[RowTuple] = []
        inserted = 0

        for row in rows:
            buf.append(row)
            if len(buf) >= chunk_size:
                inserted += await self._flush(session, buf)
                buf.clear()

        if buf:
            inserted += await self._flush(session, buf)

        return inserted

    async def _flush(self, session: AsyncSession, rows: List[RowTuple]) -> int:
        """Запись одного чанка + commit."""
        stmt = (
            pg_insert(Item)
            .values([{"code": c, "name": n, "unit": u, "type": t} for (c, n, u, t) in rows])
            .on_conflict_do_nothing(index_elements=[Item.code])
        )
        await session.execute(stmt)
        await session.commit()
        return len(rows)

    async def fetch_all_item_ids_and_names(self, session: AsyncSession) -> List[Tuple[int, str]]:
        """Список (id, name) для индексации/матчинга."""
        res = await session.execute(select(Item.id, Item.name).order_by(Item.id))
        return [(int(i), str(n)) for (i, n) in res.all()]

    async def fetch_item_name_unit_by_id(
        self,
        session: AsyncSession,
        item_id: int,
    ) -> Optional[Tuple[str, Optional[str]]]:
        """(name, unit) по id."""
        res = await session.execute(select(Item.name, Item.unit).where(Item.id == int(item_id)))
        row = res.first()
        return (str(row[0]), row[1]) if row else None

    async def fetch_item_name_unit_code_by_id(
        self,
        session: AsyncSession,
        item_id: int,
    ) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
        """(name, unit, code) по id."""
        res = await session.execute(select(Item.name, Item.unit, Item.code).where(Item.id == int(item_id)))
        row = res.first()
        return (str(row[0]), row[1], row[2]) if row else None

    async def fetch_item_codes(
        self,
        session: AsyncSession,
        item_ids: Sequence[int],
    ) -> Dict[int, Optional[str]]:
        """Мапа id->code."""
        if not item_ids:
            return {}

        ids = sorted({int(i) for i in item_ids if i is not None})
        if not ids:
            return {}

        res = await session.execute(select(Item.id, Item.code).where(Item.id.in_(ids)))
        return {int(i): (c if c is not None else None) for (i, c) in res.all()}

    async def fetch_items_meta_by_ids(
        self,
        session: AsyncSession,
        item_ids: Sequence[int],
    ) -> Dict[int, Tuple[str, Optional[str], Optional[str]]]:
        """Батч: id -> (name, unit, code)."""
        if not item_ids:
            return {}

        ids = sorted({int(i) for i in item_ids if i is not None})
        if not ids:
            return {}

        res = await session.execute(
            select(Item.id, Item.name, Item.unit, Item.code).where(Item.id.in_(ids))
        )

        out: Dict[int, Tuple[str, Optional[str], Optional[str]]] = {}
        for item_id, name, unit, code in res.all():
            out[int(item_id)] = (
                str(name),
                unit if unit is not None else None,
                code if code is not None else None,
            )
        return out

    async def search_items(
            self,
            session: AsyncSession,
            *,
            query: str,
            limit: int = 20,
    ) -> List[Item]:
        """
        Быстрый поиск items для UI (dropdown/AJAX).

        Ищем по:
          - code ILIKE %q%
          - name ILIKE %q%

        Сортируем так, чтобы совпадения по code были выше,
        а дальше — по code (стабильно).
        """
        q = (query or "").strip()
        if len(q) < 2:
            return []

        like = f"%{q}%"
        stmt = (
            select(Item)
            .where(or_(Item.code.ilike(like), Item.name.ilike(like)))
            .order_by(
                case((Item.code.ilike(like), 0), else_=1),
                Item.code.asc(),
                Item.id.asc(),
            )
            .limit(int(limit))
        )

        res = await session.execute(stmt)
        return list(res.scalars().all())