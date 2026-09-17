"""证据质检 Agent：阻止缺少原文或法律依据的风险结论直接被信任。"""
from __future__ import annotations

from app.agent.base import BaseAgent
from app.agent.state import AgentState


class QualityGateAgent(BaseAgent):
    name = "quality_gate"
    description = "✅ 证据质检 — 正在核验风险依据…"
    system_prompt = ""
    skills: list[str] = []

    async def run(self, state: AgentState) -> AgentState:
        issues: list[str] = []
        for risk in state.risk_assessments:
            if not risk.original_clause or risk.original_clause not in state.raw_text:
                issues.append(f"{risk.title}: 原文定位待人工复核")
            if not risk.legal_basis.strip():
                issues.append(f"{risk.title}: 缺少法律依据")
        state.quality_issues = issues
        state.confidence_score = max(0, 100 - min(60, len(issues) * 15))
        return state
