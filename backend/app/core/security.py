"""
安全与鉴权模块.

提供可选的 API Key 鉴权和 JWT 用户认证。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt

import bcrypt

from app.core.config import get_settings

settings = get_settings()

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """创建 JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT token."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


async def verify_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """
    验证 API Key.

    - 如果服务端未配置 api_secret_key，则跳过鉴权（开发友好）。
    - 如果配置了 api_secret_key，则必须在请求头中携带有效 Key。
    """
    if not settings.auth_enabled:
        return None

    if not api_key or api_key != settings.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无效的 API Key",
        )
    return api_key


async def get_optional_token(token: str | None = Security(_oauth2_scheme)) -> str | None:
    """可选的 JWT token 解析 (用于同时兼容 API Key 和 JWT)."""
    return token
