"""
# path: src/app_logging.py

Единый JSON-логгер для проекта.

ВАЖНО:
- Файл НЕ должен называться logging.py, иначе он перекрывает стандартный модуль `logging`
  и ломает Poetry/uvicorn (они импортируют stdlib logging на старте).
- Здесь реализован LoggerAdapter, который добавляет в JSON:
  time, level, func, message (+ optional extra).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """Форматтер, превращающий LogRecord в JSON строку."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "func": record.funcName,
            "message": record.getMessage(),
        }

        extra: Optional[Dict[str, Any]] = getattr(record, "extra", None)
        if isinstance(extra, dict) and extra:
            payload.update(extra)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class JsonLoggerAdapter(logging.LoggerAdapter):
    """LoggerAdapter, который безопасно прокидывает user extra в record.extra."""

    def process(self, msg: str, kwargs: Dict[str, Any]):
        user_extra = kwargs.pop("extra", None)
        kwargs["extra"] = {"extra": user_extra} if user_extra else {}
        return msg, kwargs


def get_logger(name: str) -> JsonLoggerAdapter:
    """Создаёт/возвращает настроенный JSON-логгер (stdout, idempotent)."""
    logger = logging.getLogger(name)
    logger.propagate = False

    if logger.handlers:
        return JsonLoggerAdapter(logger, {})

    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())

    logger.addHandler(handler)
    return JsonLoggerAdapter(logger, {})
