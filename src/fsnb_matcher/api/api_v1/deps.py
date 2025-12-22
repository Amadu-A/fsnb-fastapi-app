# path: src/fsnb_matcher/api/api_v1/deps.py
from __future__ import annotations

from functools import lru_cache

from src.crud.item_repository import IItemRepository, ItemRepository


@lru_cache(maxsize=1)
def _repo_singleton() -> ItemRepository:
    """
    Singleton репозитория.

    Почему:
    - репозиторий сам по себе статeless, держать один экземпляр безопасно;
    - экономим лишние аллокации.
    """
    return ItemRepository()


def get_item_repository() -> IItemRepository:
    """
    FastAPI Depends-провайдер.

    Возвращаем интерфейс (IItemRepository), чтобы соблюсти твой DI-паттерн.
    """
    return _repo_singleton()
