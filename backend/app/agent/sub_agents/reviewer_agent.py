"""
Reviewer Agent — 风险审查子智能体.

综合条款和法规进行逐项风险评估和整体打分; 审查完成后在节点内联执行
证据质检 (原独立 quality_gate 节点并入): 核验原文定位与法律依据,
产出置信度与待人工复核清单。
"""

from __future__ import annotations

import json
import re

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentState, RiskAssessment
from app.models.analysis import RiskCategory, RiskLevel
from app.mcp.client import MCPClient
from app.agent.playbooks import render_playbook

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

# ── 法律依据溯源: 正则与数字归一 ──────────────────────────────

# 从自由文本的 legal_basis 中抽取『法名』(《...》) 与『条号』(第X条, 中文/阿拉伯数字)
_LAW_NAME_RE = re.compile(r"《([^》]{2,20}?)》")
_ARTICLE_RE = re.compile(r"第([〇○零一二三四五六七八九十百千0-9]{1,8})条")

_CN_DIGITS = {
    "零": 0, "〇": 0, "○": 0,
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _cn_numeral_to_int(token: str) -> int | None:
    """将中文或阿拉伯数字归一为整数 (支持到千位), 无法解析返回 None."""
    token = re.sub(r"\s+", "", token)
    if not token:
        return None
    if token.isdigit():
        return int(token)
    total = 0
    num = 0
    for ch in token:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            total += (num if num else 1) * _CN_UNITS[ch]
            num = 0
        else:
            return None
    return total + num


def _normalize_law(name: str) -> str:
    """去掉法名中的书名号与空白, 便于子串比对."""
    return re.sub(r"[《》\s]", "", name)


def _legal_basis_traceable(legal_basis: str, references: list) -> bool:
    """核验 legal_basis 引用的『法名+条号』能否在检索结果中溯源.

    要求同时抽取到法名与条号, 并存在某条检索结果同时匹配二者才算命中;
    只给法名或只给条号 (如规则降级的模糊提示) 均视为不可溯源。
    """
    if not references:
        return False

    cited_laws = [_normalize_law(m) for m in _LAW_NAME_RE.findall(legal_basis)]
    cited_articles: set[int] = set()
    for token in _ARTICLE_RE.findall(legal_basis):
        value = _cn_numeral_to_int(token)
        if value is not None:
            cited_articles.add(value)

    if not cited_laws or not cited_articles:
        return False

    for ref in references:
        match = _ARTICLE_RE.search(ref.article)
        if not match:
            continue
        ref_article = _cn_numeral_to_int(match.group(1))
        if ref_article is None or ref_article not in cited_articles:
            continue
        ref_law = _normalize_law(ref.law_name)
        if ref_law and any(ref_law in law or law in ref_law for law in cited_laws):
            return True
    return False



class ReviewerAgent(BaseAgent):
    """风险审查子智能体."""

    name = "reviewer"
    description = "🔍 风险审查 — 正在评估风险并核验依据…"
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

        self._apply_quality_gate(state)
        return state

    @staticmethod
    def _build_context(state: AgentState) -> str:
        parts = [render_playbook(), "\n## 合同条款:\n"]
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

    @staticmethod
    def _apply_quality_gate(state: AgentState) -> None:
        """证据质检 (原独立 quality_gate 节点并入本节点).

        阻止缺少原文、法律依据为空或无法溯源的风险结论直接被信任: 逐条核验
        ``original_clause`` 能否定位到合同原文、``legal_basis`` 是否为空, 并将
        ``legal_basis`` 中抽取的『法名+条号』与 ``legal_references`` 逐条比对,
        命中不了则追加『依据待人工复核』标注; 汇总待人工复核清单并折算证据完整性置信度。
        """
        issues: list[str] = []
        for risk in state.risk_assessments:
            if not risk.original_clause or risk.original_clause not in state.raw_text:
                issues.append(f"{risk.title}: 原文定位待人工复核")
            if not risk.legal_basis.strip():
                issues.append(f"{risk.title}: 缺少法律依据")
            elif not _legal_basis_traceable(risk.legal_basis, state.legal_references):
                issues.append(f"{risk.title}: 法律依据无法溯源，依据待人工复核")
        state.quality_issues = issues
        state.confidence_score = max(0, 100 - min(60, len(issues) * 15))
