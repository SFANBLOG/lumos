"""
合同分析后台任务管理.

将 ``run_contract_analysis`` 的执行与 SSE 连接解耦:

- 提交合同后立即以后台 asyncio 任务运行, 使用独立数据库会话;
- 事件按序缓存在进程内存, SSE 端点只做「回放 + 跟随推送」,
  客户端断线/离开页面不再中断分析, 重连可看到完整进度;
- 进程重启丢失的在途任务由启动对账 (reconcile_orphans) 标记失败;
- 事件缓冲为进程内状态, 要求 uvicorn 单 worker 运行
  (deploy/supervisord.conf --workers 1), 多 worker 需改外置队列。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from loguru import logger

from app.agent.graph import run_contract_analysis
from app.core.database import async_session_factory
from app.models.contract import Contract, ContractStatus
from app.schemas.analysis import SSEEvent, SSEEventType

#: 已结束的会话缓冲最多保留多少个 (超出按插入顺序淘汰)
_MAX_KEPT_SESSIONS = 50

#: 无终态事件时等待分析的兜底超时 (秒), 防 LLM 挂死导致任务永动
_TASK_TIMEOUT = 900.0


class _TaskSession:
    __slots__ = ("events", "done", "task")

    def __init__(self) -> None:
        self.events: list[SSEEvent] = []
        self.done: bool = False
        self.task: asyncio.Task | None = None


_sessions: dict[str, _TaskSession] = {}


def has_session(contract_id: str) -> bool:
    """该合同是否已有内存中的分析会话 (在途或可回放)."""
    return contract_id in _sessions


def start_analysis(contract_id: str, raw_text: str) -> None:
    """启动后台分析任务; 已有会话 (在途或已缓冲) 时不重复执行."""
    if contract_id in _sessions:
        return
    _prune()
    sess = _TaskSession()
    _sessions[contract_id] = sess
    sess.task = asyncio.create_task(
        _runner(contract_id, raw_text, sess),
        name=f"analysis:{contract_id}",
    )
    logger.info(f"🚀 后台分析任务已启动 | 合同ID: {contract_id}")


async def stream_events(contract_id: str) -> AsyncGenerator[SSEEvent, None]:
    """回放已缓冲事件并跟随推送, 直到任务结束."""
    sess = _sessions.get(contract_id)
    if sess is None:
        return
    idx = 0
    while True:
        while idx < len(sess.events):
            yield sess.events[idx]
            idx += 1
        if sess.done and idx >= len(sess.events):
            return
        await asyncio.sleep(0.2)


async def reconcile_orphans() -> None:
    """启动对账: 进程重启后内存任务已失, 孤儿 analyzing 记录标记失败."""
    async with async_session_factory() as session:
        from sqlmodel import select

        stmt = select(Contract).where(Contract.status == ContractStatus.ANALYZING)
        rows = (await session.execute(stmt)).scalars().all()
        for contract in rows:
            contract.status = ContractStatus.FAILED
            contract.updated_at = datetime.now(UTC)
            session.add(contract)
        if rows:
            await session.commit()
            logger.warning(f"🧹 启动对账 | {len(rows)} 条孤儿 analyzing 记录已标记失败")


async def _runner(contract_id: str, raw_text: str, sess: _TaskSession) -> None:
    terminal: ContractStatus | None = None
    try:
        async with asyncio.timeout(_TASK_TIMEOUT):
            async with async_session_factory() as session:
                async for event in run_contract_analysis(
                    contract_id=contract_id,
                    raw_text=raw_text,
                    session=session,
                ):
                    if event.event == SSEEventType.COMPLETE:
                        # 先落库再入缓冲: 客户端收到 COMPLETE 后立即查报告不会扑空
                        await _set_status(session, contract_id, ContractStatus.COMPLETED)
                        terminal = ContractStatus.COMPLETED
                    elif event.event == SSEEventType.ERROR:
                        await _set_status(session, contract_id, ContractStatus.FAILED)
                        terminal = ContractStatus.FAILED
                    sess.events.append(event)
    except TimeoutError:
        logger.error(f"⏰ 后台分析任务超时 ({_TASK_TIMEOUT:.0f}s) | 合同ID: {contract_id}")
        sess.events.append(
            SSEEvent(event=SSEEventType.ERROR, data={"message": "分析超时, 已标记失败, 请重新提交"})
        )
    except Exception:
        logger.exception(f"❌ 后台分析任务异常 | 合同ID: {contract_id}")
        sess.events.append(
            SSEEvent(event=SSEEventType.ERROR, data={"message": "分析引擎异常, 任务已标记失败"})
        )
    finally:
        if terminal is None:
            try:
                async with async_session_factory() as session:
                    await _set_status(session, contract_id, ContractStatus.FAILED)
            except Exception:
                logger.exception(f"后台分析任务失败状态落库异常 | 合同ID: {contract_id}")
        sess.done = True


async def _set_status(session, contract_id: str, new_status: ContractStatus) -> None:
    contract = await session.get(Contract, contract_id)
    if contract is not None:
        contract.status = new_status
        contract.updated_at = datetime.now(UTC)
        session.add(contract)
        await session.commit()


def _prune() -> None:
    done_ids = [cid for cid, s in _sessions.items() if s.done]
    overflow = len(done_ids) - _MAX_KEPT_SESSIONS
    for cid in done_ids[: max(overflow, 0)]:
        _sessions.pop(cid, None)
