"""
数据库引擎与会话管理.

使用 SQLModel + aiomysql 提供异步 MySQL 支持。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.core.config import get_settings

settings = get_settings()

# 异步引擎
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
    pool_pre_ping=True,
)

# 异步会话工厂
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """应用启动时创建表，并为旧版 MySQL 做可重复执行的小型迁移。"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        # SQLModel 的 create_all 不会对已有表新增字段。role 是认证读取的
        # 必需字段，缺失时注册/登录会直接 500；仅在 MySQL 中按需补列。
        if engine.url.get_backend_name() == "mysql":
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
                    "AND COLUMN_NAME = 'role'"
                )
            )
            if result.scalar_one() == 0:
                # 多 worker 会同时执行 lifespan；MySQL 8 的 IF NOT EXISTS
                # 让并发启动时只有一个 worker 真正变更 schema。
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'member'")
                )
            # 早期迁移使用了小写默认值，而 SQLAlchemy Enum 默认存储成员名
            # （MEMBER/ADMIN/...）。统一历史值，避免读取已有用户时抛 LookupError。
            await conn.execute(
                text(
                    "UPDATE users SET role = UPPER(role) "
                    "WHERE role IN ('owner', 'admin', 'auditor', 'member')"
                )
            )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入: 获取数据库会话."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
