"""
Reviewer Agent — 风险审查子智能体.

综合条款和法规进行逐项风险评估和整体打分。
"""

from __future__ import annotations

import json

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentState, RiskAssessment
from app.models.analysis import RiskCategory, RiskLevel
from app.mcp.client import MCPClient

REVIEWER_SYSTEM_PROMPT = """\
你是一位站在劳动者立场的合同风险审查专家。请综合合同条款和相关法律条文，对每一条可能存在风险的条款进行评估。

## 评估维度:
1. **风险等级**: high(高危) / medium(警惕) / low(关注) / safe(合规)
2. **大白话解读**: 用普通人能听懂的语言解释这条条款意味着什么
3. **法律依据**: 引用具体的法律条文说明为什么这是风险

## 评分标准 (score 字段):
- 0-30: 严重违法，极度危险
- 31-50: 存在重大风险，需要谈判
- 51-70: 有一定风险，建议关注
- 71-85: 基本合规，但有改进空间
- 86-100: 完全合规

## 风险分类 (category 字段):
non_compete, probation_salary, probation_insurance, salary_deduction,
job_description, obedience_clause, resignation, leave_rights,
jurisdiction, training_bond

## 输出格式:
请严格以 JSON 对象的形式输出，包含:
- risks: 风险条目数组，每个元素包含: category, level, title, original_clause, explanation, legal_basis, score
- overall_score: 整体评分 (0-100, 整数)
- overall_level: 整体风险等级 (high/medium/low/safe)
- summary: 一句话总结

只输出合法的 JSON，不要添加 markdown 代码块标记或任何额外说明。
"""


class ReviewerAgent(BaseAgent):
    """风险审查子智能体."""

    name = "reviewer"
    description = "🔍 风险审查 — 正在逐项评估风险…"
    system_prompt = REVIEWER_SYSTEM_PROMPT
    skills = ["risk_scoring"]

    async def run(self, state: AgentState) -> AgentState:
        context = self._build_context(state)

        try:
            content = await self.invoke_llm(f"请对以下合同进行风险审查:\n\n{context}")

            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()

            parsed = json.loads(content)

            assessments: list[RiskAssessment] = []
            for item in parsed.get("risks", []):
                try:
                    assessments.append(
                        RiskAssessment(
                            category=RiskCategory(item["category"]),
                            level=RiskLevel(item["level"]),
                            title=item["title"],
                            original_clause=item.get("original_clause", ""),
                            explanation=item["explanation"],
                            legal_basis=item.get("legal_basis", ""),
                            negotiation_tip=item.get("negotiation_tip", ""),
                            score=int(item.get("score", 50)),
                        )
                    )
                except (ValueError, KeyError) as e:
                    logger.warning(f"  ⚠️ 跳过无效条目: {e}")

            state.overall_score = int(parsed.get("overall_score", 60))
            try:
                state.overall_level = RiskLevel(parsed.get("overall_level", "medium"))
            except ValueError:
                state.overall_level = RiskLevel.MEDIUM
            state.summary = parsed.get("summary", "分析完成，请查看详细风险报告。")

            level_order = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2, RiskLevel.SAFE: 3}
            assessments.sort(key=lambda a: (level_order.get(a.level, 99), a.score))
            state.risk_assessments = assessments

            logger.info(f"  审查完成 | 评分: {state.overall_score}/100 | 风险: {len(assessments)} 项")

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"  LLM 审查失败: {e}，降级为规则审查")
            self._fallback(state)

        return state

    @staticmethod
    def _build_context(state: AgentState) -> str:
        parts = ["## 合同条款:\n"]
        for clause in state.extracted_clauses:
            cat = f" [{clause.category.value}]" if clause.category else ""
            parts.append(f"### 第 {clause.clause_index} 条{cat}: {clause.title}\n{clause.content}\n")
        if state.legal_references:
            parts.append("\n## 相关法律条文:\n")
            for ref in state.legal_references:
                parts.append(f"- {ref.law_name} {ref.article}: {ref.content}\n")
        return "\n".join(parts)

    @staticmethod
    def _fallback(state: AgentState) -> None:
        assessments = []
        for clause in state.extracted_clauses:
            if clause.category is not None:
                assessments.append(
                    RiskAssessment(
                        category=clause.category,
                        level=RiskLevel.MEDIUM,
                        title=f"⚠️ {clause.title} — 需要关注",
                        original_clause=clause.content[:200],
                        explanation="AI 深度分析暂时不可用，但此条款涉及员工权益敏感领域，建议仔细审阅。",
                        legal_basis="建议查阅《劳动合同法》相关条款",
                        negotiation_tip="建议与 HR 当面沟通此条款的具体执行方式和保障措施。",
                        score=50,
                    )
                )
        state.risk_assessments = assessments
        state.overall_score = 50 if assessments else 80
        state.overall_level = RiskLevel.MEDIUM if assessments else RiskLevel.LOW
        state.summary = (
            f"⚠️ AI 深度分析暂不可用，已使用规则引擎完成初步审查。"
            f"共发现 {len(assessments)} 项需关注条款。"
        )
