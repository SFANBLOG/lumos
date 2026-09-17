"""合同运营 Agent：提取合同要素和需要持续跟进的义务。"""
from __future__ import annotations

import re

from app.agent.base import BaseAgent
from app.agent.state import AgentState


class ObligationAgent(BaseAgent):
    name = "obligation"
    description = "📅 合同运营 — 正在提取期限与义务…"
    system_prompt = ""
    skills: list[str] = []

    async def run(self, state: AgentState) -> AgentState:
        text = state.raw_text
        dates = re.findall(r"20\d{2}年\d{1,2}月\d{1,2}日|20\d{2}[-/]\d{1,2}[-/]\d{1,2}", text)
        amounts = re.findall(r"(?:人民币|¥|￥)?\s*\d+(?:\.\d+)?\s*(?:元|万元|万元/年|元/月)", text)
        keywords = {"自动续约": "核查续约窗口", "保密": "持续保密义务", "竞业": "竞业限制义务", "培训": "培训服务期义务", "社保": "社保缴纳义务"}
        obligations = [label for key, label in keywords.items() if key in text]
        state.contract_facts = {"dates": dates[:10], "amounts": amounts[:10], "obligations": obligations, "auto_renewal": "自动续约" in text}
        return state
