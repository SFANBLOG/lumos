"""
Coordinator Agent — 多智能体团队的监督者 / 调度者.

它不是流水线上的一个「步骤」, 而是有独立决策权的自治智能体:
读取合同原文后自行决定本次审查由哪些智能体参与 (编排计划),
再通过消息总线向每个参与者下发 task 消息。图的条件边读取
``agent_plan`` 决定 reviewer 之后是否进入独立复核环节。

调度采用确定性规则而非 LLM, 原因是编排决策必须可复现、可审计,
不能让「谁来审」这件事本身再引入一层模型不确定性。
"""

from __future__ import annotations

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentMessage, AgentState

#: 完整审查链路 (含独立复核)
_FULL_PLAN = ["extractor", "retriever", "reviewer", "verifier", "negotiator"]
#: 极短文本的精简链路 (跳过独立复核, 避免小合同上过度编排)
_LITE_PLAN = ["extractor", "retriever", "reviewer", "negotiator"]

#: 低于此长度视为极短文本
_LITE_TEXT_THRESHOLD = 120


class CoordinatorAgent(BaseAgent):
    """协调调度智能体: 编排参与者、分派任务、初始化协作轮次."""

    name = "coordinator"
    description = "🧭 协调调度 — 正在分派审查任务…"
    system_prompt = (
        "你是劳动合同审查多智能体团队的协调者。根据合同规模决定参与的智能体，"
        "把任务分派给抽取、检索、审查、复核、谈判各角色，并监督复核结论。"
    )
    skills = ["planning", "routing", "delegation"]

    async def run(self, state: AgentState) -> AgentState:
        text_len = len(state.raw_text.strip())
        plan = list(_LITE_PLAN if text_len < _LITE_TEXT_THRESHOLD else _FULL_PLAN)

        state.agent_plan = plan
        state.review_rounds = 0
        state.verdict = ""
        state.agent_messages.append(
            AgentMessage(
                sender=self.name,
                recipient="broadcast",
                kind="plan",
                content=f"合同长度 {text_len} 字；本次编排: {' → '.join(plan)}",
                round=0,
            )
        )
        for participant in plan:
            state.agent_messages.append(
                AgentMessage(
                    sender=self.name,
                    recipient=participant,
                    kind="task",
                    content=f"请执行 {participant} 职责，完成后广播 result 消息",
                    round=0,
                )
            )

        logger.info(f"🧭 [{self.name}] 编排完成 | 参与智能体: {plan}")
        return state
