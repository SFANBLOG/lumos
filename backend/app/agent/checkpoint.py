"""
LangGraph 检查点 (Checkpointer).

三种后端由 ``CHECKPOINT_BACKEND`` 切换:

- ``off``    : 不注入检查点 (旧行为, 图仍可正常运行);
- ``memory`` : 默认, 进程内 InMemorySaver; 每个节点执行后落一份状态快照,
               同一 thread_id 可查询历史 / 从挂起点续跑, 进程重启后失效;
- ``sqlite`` : 本地 SQLite 文件, 跨进程重启仍可续跑, 适合单机单 worker 部署。

检查点以 ``contract_id`` 作为 thread_id。多机 / 多 worker 部署需换成外置
PostgresSaver 并让所有进程指向同一库 (见 README 部署说明)。
"""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from loguru import logger

from app.core.config import BASE_DIR, get_settings

#: 默认落盘位置 (backend/var/checkpoints.sqlite)
DEFAULT_SQLITE_PATH = BASE_DIR / "var" / "checkpoints.sqlite"


def _sqlite_path() -> Path:
    configured = get_settings().checkpoint_sqlite_path.strip()
    return Path(configured) if configured else DEFAULT_SQLITE_PATH


def _create_checkpointer() -> BaseCheckpointSaver[Any] | None:
    backend = get_settings().checkpoint_backend.strip().lower()
    if backend == "off":
        logger.info("💾 检查点: 已关闭 (off)")
        return None
    if backend == "sqlite":
        try:
            import aiosqlite
            from langgraph.checkpoint.sqlite import SqliteSaver
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        except ImportError as exc:  # pragma: no cover - 仅在依赖缺失时触发
            raise RuntimeError(
                "CHECKPOINT_BACKEND=sqlite 需要 langgraph-checkpoint-sqlite 与 aiosqlite"
            ) from exc
        path = _sqlite_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        # 建表用同步连接一次完成 (CREATE TABLE IF NOT EXISTS, 可重复执行)
        bootstrap = sqlite3.connect(str(path), check_same_thread=False)
        try:
            SqliteSaver(bootstrap).setup()
        finally:
            bootstrap.close()

        # 图走 astream 异步路径, 必须用 AsyncSqliteSaver;
        # 同步版 SqliteSaver 的 aget_tuple/aput 会抛 NotImplementedError。
        conn = aiosqlite.connect(str(path), check_same_thread=False)
        conn._thread.daemon = True  # 进程级单例, 服务退出时无需等待该线程

        async def _connect() -> AsyncSqliteSaver:
            await conn  # 启动 aiosqlite 后台线程并建立真实 sqlite 连接
            return AsyncSqliteSaver(conn)

        # 工厂是同步函数 (可能在运行中的 loop 内被调用), 因此在独立线程里
        # 用一次性 loop 完成连接初始化。之后 saver 每次 _execute 都在调用方
        # 的运行 loop 里新建 future, aiosqlite 通过 future.get_loop() 回传结果。
        with ThreadPoolExecutor(max_workers=1) as pool:
            saver: BaseCheckpointSaver[Any] = pool.submit(
                lambda: asyncio.run(_connect())
            ).result()
        logger.info(f"💾 检查点: SQLite (async) | {path}")
        return saver
    logger.info("💾 检查点: 进程内存 (InMemorySaver)")
    return InMemorySaver()


@lru_cache(maxsize=1)
def get_checkpointer() -> BaseCheckpointSaver[Any] | None:
    """进程级单例: 同一 saver 必须被编译后的图与状态查询共用."""
    return _create_checkpointer()


def reset_checkpointer() -> None:
    """清空单例 (切换后端 / 测试隔离时调用, 需同时清 build_contract_graph 缓存).

    顺带关闭旧的 sqlite 异步连接, 避免反复 reset 造成连接泄漏。
    """
    saver = get_checkpointer() if get_checkpointer.cache_info().currsize else None
    if saver is not None:
        close = getattr(getattr(saver, "conn", None), "close", None)
        if close is not None and inspect.iscoroutinefunction(close):
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(lambda: asyncio.run(close())).result(timeout=3)
            except Exception:  # noqa: BLE001
                logger.debug("旧检查点连接关闭失败 (可忽略)")
    get_checkpointer.cache_clear()


def graph_config(
    thread_id: str, *, checkpoint_id: str | None = None, **extra: Any
) -> dict[str, Any]:
    """构造 LangGraph RunnableConfig: thread_id 是检查点的主键.

    ``checkpoint_id`` 非空时表示「从指定历史快照分叉续跑」。
    """
    configurable: dict[str, Any] = {"thread_id": thread_id}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    config: dict[str, Any] = {"configurable": configurable}
    config.update(extra)
    return config
