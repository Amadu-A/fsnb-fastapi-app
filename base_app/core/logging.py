# /base_app/core/logging.py
from __future__ import annotations

import json
import logging
from logging import LoggerAdapter
from time import time


class JsonFormatter(logging.Formatter):
    """Простой JSON-форматтер: время, уровень, логгер, сообщение/данные."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload = {
            "ts": round(time(), 3),
            "level": record.levelname,
            "logger": record.name,
        }
        # Если передали dict в msg — включаем "как есть"
        if isinstance(record.msg, dict):
            payload.update(record.msg)
        else:
            payload["message"] = record.getMessage()
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str, base_level: int = logging.INFO) -> LoggerAdapter:
    """Возвращает LoggerAdapter с JSON-форматированием."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(base_level)
    # LoggerAdapter позволяет передавать .info({...}) и добавлять extra при необходимости
    return LoggerAdapter(logger, extra={})
