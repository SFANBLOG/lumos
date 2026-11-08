"""
Verifier Agent — 独立复核智能体 (可否决审查结论).

与 Reviewer 不同, 它不产出风险结论, 而是站在「挑错」立场交叉验证:
逐条核验原文能否在合同中定位、法条依据能否在检索结果中溯源、
高危条目是否有依据。发现问题时向 Reviewer 发送 rework 消息,
由 LangGraph 条件边把流程退回 Reviewer 重审 (受 max_review_rounds 限制);
通过时向 Negotiator 发送 handoff 消息放行。

复核用确定性规则而非 LLM, 避免「用模型审模型」引入新的不确定性,
同时保证每次返工的触发原因都可在消息总线里回溯。
"""

from __future__ import annotations

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentMessage, AgentState
from app.agent.sub_agents.reviewer_agent import _legal_basis_traceable
from app.models.analysis import RiskLevel


class VerifierAgent(BaseAgent):
    """独立复核智能体: 交叉验证依据与结论, 必要时发起返工."""

    name = "verifier"
    description = "🧪 独立复核 — 正在交叉验证依据与结论…"
    system_prompt = (
        "你是独立的合同审查复核员。不信任审查员的结论，逐条核对原文定位与法律依据，"
        "发现问题就退回重审，通过才放行到谈判环节。"
    )
    skills = ["cross_check", "veto", "handoff"]

    async def run(self, state: AgentState) -> AgentState:
        reasons = self._check(state)
        can_rework = (
            bool(reasons)
            and not state.ai_degraded
            and state.review_rounds < state.max_review_rounds
        )

        if can_rework:
            state.review_rounds += 1
            state.verdict = "rework"
            state.agent_messages.append(
                AgentMessage(
                    sender=self.name,
                    recipient="reviewer",
                    kind="rework",
                    content="；".join(reasons),
                    round=state.review_rounds,
                )
            )
            logger.warning(f"🧪 [{self.name}] 复核不通过, 发起第 {state.review_rounds} 轮返工")
        else:
            state.verdict = "approve"
            if reasons:
                # 达到返工上限或 AI 已降级: 不再循环, 但把问题显式留给人工复核
                state.quality_issues = list(dict.fromkeys([*state.quality_issues, *reasons]))
            state.agent_messages.append(
                AgentMessage(
                    sender=self.name,
                    recipient="negotiator",
                    kind="handoff",
                    content=(
                        f"复核通过 (轮次 {state.review_rounds}/{state.max_review_rounds})"
                        + (f"；遗留待人工复核: {len(reasons)} 项" if reasons else "")
                    ),
                    round=state.review_rounds,
                )
            )
            logger.info(f"🧪 [{self.name}] 复核通过 | 遗留问题: {len(reasons)} 项")
        return state

    @staticmethod
    def _check(state: AgentState) -> list[str]:
        """返回本次审查中发现的、应由 Reviewer 重审或人工复核的问题."""
        reasons: list[str] = []
        if state.ai_degraded:
            reasons.append("审查引擎降级，结论不可作为依据")

        for risk in state.risk_assessments:
            if not risk.original_clause or risk.original_clause not in state.raw_text:
                reasons.append(f"{risk.title}: 原文定位不可回溯")
            if not risk.legal_basis.strip():
                reasons.append(f"{risk.title}: 缺少法律依据")
            elif not _legal_basis_traceable(risk.legal_basis, state.legal_references):
                reasons.append(f"{risk.title}: 法条依据无法溯源")
            if risk.level == RiskLevel.HIGH and not risk.legal_basis.strip():
                reasons.append(f"{risk.title}: 高危条目无依据")

        return list(dict.fromkeys(reasons))
