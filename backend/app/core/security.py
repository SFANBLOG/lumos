"""
安全与鉴权模块.

提供 JWT 用户认证与 bcrypt 密码哈希。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets

from jose import JWTError, jwt

import bcrypt

from app.core.config import get_settings

settings = get_settings()


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


def create_captcha_challenge() -> tuple[str, str]:
    """生成五分钟有效、由服务端签名的算术验证码挑战。"""
    left = secrets.randbelow(9) + 1
    right = secrets.randbelow(9) + 1
    token = jwt.encode(
        {"type": "captcha", "answer": str(left + right), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return f"{left} + {right} = ?", token


def verify_captcha_challenge(token: str, answer: str) -> bool:
    """验证验证码签名、有效期和答案。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("type") == "captcha" and secrets.compare_digest(str(payload.get("answer", "")), answer.strip())
    except JWTError:
        return False
