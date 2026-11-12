"""逐条条款改写引擎 (redline v2).

v1 只按风险类别返回固定模板，同一类别的每条条款拿到同一句建议。
v2 做到「逐条」：

- Reviewer 的 LLM 在输出风险时一并给出 ``revised_clause`` / ``rewrite_reason``
  （不增加 LLM 调用次数、不改变图拓扑），由本模块做格式校验后采用；
- LLM 未给、给得不合法或 AI 降级时，按**本条原文**做规则兜底：
  原句业务约定保留并追加法定约束，若原句本身与法律冲突则整条替换；
- 每条都产出 ``original → revised`` 的 unified diff、改写理由、
  生成方式（llm / rule）与置信度，可落库、可导出、可审计。
"""

from __future__ import annotations

import difflib
import re
from pydantic import BaseModel, Field

from app.agent.redline import build_revision

#: 原句本身与法定要求直接冲突时，不做「追加」而是整条替换
_CONFLICT_RE = re.compile(
    r"自愿放弃|不缴|无需缴纳|不予缴纳|不得主张|无条件服从|需经批准|"
    r"概不负责|公司有权随时|不予支付|自动放弃|不得提出异议",
)
_LLM_MIN_LEN = 8
_LLM_MAX_LEN = 1200


class ClauseRewrite(BaseModel):
    """一条可审计的条款改写结果."""

    original: str = ""
    revised: str = ""
    reason: str = ""
    legal_basis: str = ""
    diff: str = Field(default="", description="unified diff, 便于与 Track Changes 对接")
    method: str = Field(default="rule", description="llm / rule / llm_invalid")
    confidence: float = Field(default=0.75, ge=0, le=1)


def _unified_diff(original: str, revised: str) -> str:
    """按标点切句生成 unified diff，中文长句也能看出改了哪一段。"""
    def split(text: str) -> list[str]:
        parts = re.split(r"(?<=[。；;，,])", text.strip())
        return [p for p in (x.strip() for x in parts) if p]

    return "\n".join(
        difflib.unified_diff(
            split(original), split(revised),
            fromfile="原条款", tofile="建议条款", lineterm="", n=1,
        )
    )


def _valid_llm_output(revised: str, original: str) -> bool:
    text = revised.strip()
    if not (_LLM_MIN_LEN <= len(text) <= _LLM_MAX_LEN):
        return False
    if text == original.strip():
        return False
    if text.startswith("{") or "```" in text:
        return False
    return True


def _rule_rewrite(original: str, category: str, legal_basis: str) -> ClauseRewrite:
    """按本条原文做规则兜底改写."""
    rule = build_revision(category)
    orig = (original or "").strip()
    conflict = bool(_CONFLICT_RE.search(orig))

    if conflict or len(orig) < 12:
        revised = rule.suggested
        reason = "原句表述与法定要求直接冲突（或过短无法保留），建议整条替换。" + rule.reason
        confidence = 0.8
    else:
        revised = orig.rstrip("。；;") + "；" + rule.suggested
        reason = "保留原约定的业务内容，追加法定约束条款。" + rule.reason
        confidence = 0.72

    return ClauseRewrite(
        original=orig,
        revised=revised,
        reason=reason,
        legal_basis=legal_basis or rule.legal_basis,
        diff=_unified_diff(orig, revised),
        method="rule",
        confidence=confidence,
    )


def build_rewrite(
    *,
    original: str,
    category: str,
    legal_basis: str = "",
    llm_revised: str = "",
    llm_reason: str = "",
) -> ClauseRewrite:
    """生成一条改写：合法 LLM 结果优先，否则按原文规则兜底."""
    if _valid_llm_output(llm_revised, original):
        revised = llm_revised.strip()
        rule = build_revision(category)
        return ClauseRewrite(
            original=(original or "").strip(),
            revised=revised,
            reason=(llm_reason or "").strip() or rule.reason,
            legal_basis=legal_basis or rule.legal_basis,
            diff=_unified_diff(original or "", revised),
            method="llm",
            confidence=0.9,
        )
    return _rule_rewrite(original, category, legal_basis)


def attach_rewrites(assessments: list) -> tuple[int, int]:
    """把改写结果写回风险条目，返回 (llm 条数, 规则兜底条数)."""
    llm_count = 0
    rule_count = 0
    for assessment in assessments:
        if getattr(assessment, "revision_method", ""):
            continue
        if getattr(assessment, "suggested_revision", "") and not getattr(
            assessment, "llm_revised_clause", ""
        ):
            # 已有人工/外部改写文本: 不覆盖, 也不冒充模型或规则生成
            continue
        category = getattr(assessment.category, "value", str(assessment.category))
        rewrite = build_rewrite(
            original=assessment.original_clause or "",
            category=category,
            legal_basis=assessment.legal_basis or "",
            llm_revised=getattr(assessment, "llm_revised_clause", "") or "",
            llm_reason=getattr(assessment, "llm_rewrite_reason", "") or "",
        )
        assessment.suggested_revision = rewrite.revised
        assessment.revision_reason = rewrite.reason
        assessment.revision_diff = rewrite.diff
        assessment.revision_method = rewrite.method
        assessment.revision_confidence = rewrite.confidence
        if rewrite.method == "llm":
            llm_count += 1
        else:
            rule_count += 1
    return llm_count, rule_count
