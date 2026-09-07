"""
API 公共依赖.

FastAPI 依赖注入: 数据库会话、鉴权等。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_session
from app.core.security import decode_access_token, verify_api_key
from app.models.user import User

# 类型别名, 在路由中直接使用
DBSession = Annotated[AsyncSession, Depends(get_session)]
AuthGuard = Annotated[str | None, Depends(verify_api_key)]


async def get_current_user(
    session: DBSession,
    authorization: str | None = None,
) -> User:
    """通过 Authorization 请求头中的 JWT 获取当前用户."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证信息",
        )

    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization

    try:
        payload = decode_access_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效的认证令牌: {e}",
        ) from e

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user
