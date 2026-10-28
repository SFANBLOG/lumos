"""
Negotiator Agent — 谈判策略子智能体.

节点内联执行合同义务提取 (原独立 obligation 节点并入): 从原文提取
期限/金额/义务要素清单; 并为每条已识别的风险生成专业的谈判话术和
沟通策略。
"""

from __future__ import annotations

import re

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentState
from app.mcp.client import MCPClient


class NegotiatorAgent(BaseAgent):
    """谈判策略子智能体."""

    name = "negotiator"
    description = "🗣️ 运营与谈判 — 正在整理义务并生成话术…"
    system_prompt = ""
    skills = ["negotiation"]

    async def run(self, state: AgentState) -> AgentState:
        _extract_obligations(state)

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


def _extract_obligations(state: AgentState) -> None:
    """合同运营要素提取 (原独立 obligation 节点并入本节点).

    提取期限、金额、义务关键词清单与自动续约标记; 不依赖风险条目,
    先于 negotiator 的无风险提前返回执行。
    """
    text = state.raw_text
    dates = re.findall(r"20\d{2}年\d{1,2}月\d{1,2}日|20\d{2}[-/]\d{1,2}[-/]\d{1,2}", text)
    amounts = re.findall(r"(?:人民币|¥|￥)?\s*\d+(?:\.\d+)?\s*(?:元|万元|万元/年|元/月)", text)
    keywords = {"自动续约": "核查续约窗口", "保密": "持续保密义务", "竞业": "竞业限制义务", "培训": "培训服务期义务", "社保": "社保缴纳义务"}
    obligations = [label for key, label in keywords.items() if key in text]
    state.contract_facts = {"dates": dates[:10], "amounts": amounts[:10], "obligations": obligations, "auto_renewal": "自动续约" in text}
