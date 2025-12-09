# /base_app/core/dependencies.py
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from .security import decode_token
from .logging import get_logger

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
log = get_logger("deps")


def get_current_subject(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Возвращает payload токена или 401.
    """
    try:
        payload = decode_token(token)
        return payload
    except JWTError as e:
        log.info({"event": "jwt_error", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
