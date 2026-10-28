"""
智能体抽象基类.

所有子智能体继承此类，实现统一的 run 接口。
"""

from __future__ import annotations

from abc import ABC
from typing import Any

from loguru import logger

from app.agent.llm import get_chat_llm
from app.agent.state import AgentState


class BaseAgent(ABC):
    """子智能体基础类."""

    name: str = ""
    description: str = ""
    system_prompt: str = ""
    skills: list[str] = []

    async def invoke_llm(
        self,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """调用 LLM 并返回文本响应."""
        llm = get_chat_llm(temperature=temperature)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        response = await llm.ainvoke(messages)
        return response.content.strip()

    async def run(self, state: AgentState) -> AgentState:
        """执行智能体任务，读写全局状态."""
        raise NotImplementedError(
            f"[{self.name}] 不参与合同状态流 (未实现 run)"
        )

    async def __call__(self, state: AgentState) -> AgentState:
        logger.info(f"🤖 [{self.name}] 开始执行 | 合同ID: {state.contract_id}")
        state.current_node = self.name
        try:
            state = await self.run(state)
            logger.info(f"✅ [{self.name}] 执行完成 | 合同ID: {state.contract_id}")
        except Exception as e:
            error_msg = f"[{self.name}] 执行失败: {e}"
            logger.error(error_msg)
            state.errors.append(error_msg)
        return state
