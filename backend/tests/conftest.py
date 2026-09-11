"""
测试公共 Fixtures.

提供测试用的 FastAPI 客户端和数据库会话。
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

# 保证从任意目录运行 pytest 都能解析 backend 根下的 app 包
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.core.database import get_session
from app.main import create_app

# 测试数据库: 与开发库 (backend/.env 的 DATABASE_URL) 同主机/凭据, 但库名固定为
# lumos_test —— 测试 fixture 会建/删表, 必须与开发库隔离, 避免污染真实数据。
# 可用环境变量 TEST_DATABASE_URL 覆盖 (例如 CI 自建的专用库)。
import os


def _default_test_db_url() -> str:
    """默认测试库地址: 解析 backend/.env 的开发库并替换库名为 lumos_test."""
    fallback = "mysql+aiomysql://lumos:lumos@localhost:3308/lumos_test"
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        return fallback
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw.startswith("DATABASE_URL=") or raw.startswith("#"):
            continue
        url = raw.split("=", 1)[1].strip().strip('"').strip("'")
        head, _, _ = url.rpartition("/")
        return f"{head}/lumos_test" if head else fallback
    return fallback


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", _default_test_db_url())


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """测试用数据库会话 (MySQL)."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """测试用 HTTP 客户端."""
    app = create_app()

    # 覆盖数据库依赖
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    # 环境启用鉴权时, 统一携带 X-API-Key 通过 AuthAny
    from app.core.config import get_settings

    settings = get_settings()
    headers = (
        {"X-API-Key": settings.api_secret_key} if settings.auth_enabled else None
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
    ) as ac:
        yield ac
