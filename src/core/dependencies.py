# /src/core/dependencies.py
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from .security import decode_token
from src.app_logging import get_logger
from src.crud import item_repository

# ВАЖНО: tokenUrl должен совпадать с реальным API-роутом получения токена
# Если у тебя токен выдаёт, например, /api/api_v1/auth/token — укажи его.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
log = get_logger("deps")


def get_current_subject(token: str = Depends(oauth2_scheme)) -> dict:
    """Возвращает payload токена или 401."""
    try:
        payload = decode_token(token)
        return payload
    except JWTError as e:
        log.info({"event": "jwt_error", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_item_repository():
    """Dependency для работы с таблицей items (используется в fsnb_matcher)."""
    return item_repository
