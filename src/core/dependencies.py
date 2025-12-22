# path: src/core/dependencies.py
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from src.app_logging import get_logger
from src.core.security import decode_token
from src.core.services.auth_service import AuthService
from src.crud.permission_repository import IPermissionRepository, PermissionRepository
from src.crud.profile_repository import IProfileRepository, ProfileRepository
from src.crud.user_repository import IUserRepository, UserRepository


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
log = get_logger("deps")


def get_current_subject(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    try:
        payload = decode_token(token)
        return payload
    except JWTError as e:
        log.info({"event": "jwt_error", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from e


@lru_cache(maxsize=1)
def _user_repo_singleton() -> UserRepository:
    return UserRepository()


def get_user_repository() -> IUserRepository:
    return _user_repo_singleton()


@lru_cache(maxsize=1)
def _profile_repo_singleton() -> ProfileRepository:
    return ProfileRepository()


def get_profile_repository() -> IProfileRepository:
    return _profile_repo_singleton()


@lru_cache(maxsize=1)
def _permission_repo_singleton() -> PermissionRepository:
    return PermissionRepository()


def get_permission_repository() -> IPermissionRepository:
    return _permission_repo_singleton()


def get_auth_service(
    user_repo: IUserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(repo=user_repo)
