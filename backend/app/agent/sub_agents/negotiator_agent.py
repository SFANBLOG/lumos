"""
Negotiator Agent — 谈判策略子智能体.

为每条已识别的风险生成专业的谈判话术和沟通策略。
"""

from __future__ import annotations

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentState
from app.mcp.client import MCPClient


class NegotiatorAgent(BaseAgent):
    """谈判策略子智能体."""

    name = "negotiator"
    description = "🗣️ 谈判策略 — 正在生成沟通话术…"
    system_prompt = ""
    skills = ["negotiation"]

    async def run(self, state: AgentState) -> AgentState:
        if not state.risk_assessments:
            logger.info("  无风险条目，跳过谈判策略生成")
            return state

        mcp = MCPClient()

        for assessment in state.risk_assessments:
            if assessment.negotiation_tip:
                continue

            category = assessment.category.value if assessment.category else None
            result = await mcp.call("negotiation", category=category)
            assessment.negotiation_tip = result.get("negotiation_tip", "")

        filled = sum(1 for a in state.risk_assessments if a.negotiation_tip)
        logger.info(f"  谈判话术生成完成 | 已填充 {filled}/{len(state.risk_assessments)} 条")
        return state
