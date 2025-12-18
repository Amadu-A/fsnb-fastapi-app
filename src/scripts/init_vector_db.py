import asyncio
from src.fsnb_matcher.services.index_qdrant import init_all_collections
from src.app_logging import get_logger

log = get_logger(__name__)

async def main():
    log.info("⏳ [init_vector_db] Индексация Qdrant начата...")
    count = await init_all_collections()
    log.info(f"✅ [init_vector_db] Индексация завершена. Всего записей: {count}")

if __name__ == "__main__":
    asyncio.run(main())
