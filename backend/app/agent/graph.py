"""
合同审查工作流入口.

通过 SupervisorAgent 编排子智能体完成完整的合同分析流程。
对外保持 run_contract_analysis 接口不变，供 SSE 流式调用。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.supervisor import SupervisorAgent
from app.schemas.analysis import SSEEvent


async def run_contract_analysis(
    contract_id: str,
    raw_text: str,
    session: AsyncSession | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """
    执行合同分析工作流, 异步生成 SSE 事件流.

    委托给 SupervisorAgent 编排所有子智能体。
    """
    logger.info(f"🚀 Agent 工作流启动 | 合同ID: {contract_id}")

    supervisor = SupervisorAgent()
    async for event in supervisor.run(
        contract_id=contract_id,
        raw_text=raw_text,
        session=session,
    ):
        yield event
