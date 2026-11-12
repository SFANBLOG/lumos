"""风险反馈回流: 从人工判定生成评测集与规则调优建议.

``RiskFeedback`` 落库后如果只用来算「采纳率」，反馈闭环仍然是断的。
本模块把反馈转成两类可消费产物:

- ``build_eval_cases``: 认可的结论 → 可并入 ``eval/goldens/review_golden.json``
  的正例; 误报的原文 → 反例集 (期望输出为空风险), 用于回归防误报;
- ``rule_tuning_suggestions``: 按风险类别聚合误报率, 达到阈值时给出可执行的
  prompt / 规则 / 阈值调优动作, 而不是只给一个百分比。

纯函数、不依赖数据库会话, 便于单测与离线批处理。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

ACCEPTED = "accepted"
FALSE_POSITIVE = "false_positive"
IGNORED = "ignored"


def _attr(obj: Any, name: str, default: str = "") -> str:
    return str(getattr(obj, name, default) or default)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def build_eval_cases(
    feedback_rows: list[Any],
    risk_rows: list[Any],
) -> dict[str, Any]:
    """反馈 → 可并入金标准的正例 + 防误报反例.

    Returns:
        ``goldens`` 可直接追加到 ``eval/goldens/review_golden.json``;
        ``negative_cases`` 供 ``generate_predictions`` 作为「应无风险」回归集。
    """
    risks = {_attr(row, "id"): row for row in risk_rows}
    positive: dict[str, dict[str, Any]] = {}
    negatives: list[dict[str, Any]] = []

    for feedback in feedback_rows:
        risk = risks.get(_attr(feedback, "risk_item_id"))
        if risk is None:
            continue
        verdict = _attr(feedback, "verdict")
        contract_id = _attr(feedback, "contract_id")
        if verdict == IGNORED or not contract_id:
            continue
        category = _enum(getattr(risk, "category", ""))
        level = _enum(getattr(risk, "level", ""))
        snippet = _attr(risk, "original_clause")
        comment = _attr(feedback, "comment")

        if verdict == FALSE_POSITIVE:
            negatives.append(
                {
                    "risk_item_id": _attr(feedback, "risk_item_id"),
                    "contract_id": contract_id,
                    "category": category,
                    "clause_snippet": snippet,
                    "comment": comment,
                    "expected_risks": [],
                }
            )
            continue
        if verdict == ACCEPTED:
            entry = positive.setdefault(
                contract_id,
                {
                    "contract_id": contract_id,
                    "group": "feedback",
                    "risks": [],
                    "missing_clauses": [],
                },
            )
            entry["risks"].append(
                {
                    "category": category,
                    "level": level or "high",
                    "clause_snippet": snippet,
                    "required": True,
                }
            )

    return {
        "goldens": list(positive.values()),
        "negative_cases": negatives,
        "positive_case_count": len(positive),
        "positive_risk_count": sum(len(g["risks"]) for g in positive.values()),
        "negative_case_count": len(negatives),
        "notice": "误报样本是反例, 不要并入金标准 risks; 应作为「期望无风险」回归用例。",
    }


def rule_tuning_suggestions(
    feedback_rows: list[Any],
    risk_rows: list[Any],
    *,
    min_samples: int = 3,
    fp_threshold: float = 0.3,
) -> dict[str, Any]:
    """按风险类别给出可执行的规则 / prompt 调优建议."""
    risks = {_attr(row, "id"): row for row in risk_rows}
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "false_positive": 0, "accepted": 0, "clauses": []}
    )

    for feedback in feedback_rows:
        risk = risks.get(_attr(feedback, "risk_item_id"))
        if risk is None:
            continue
        category = _enum(getattr(risk, "category", "")) or "unknown"
        verdict = _attr(feedback, "verdict")
        if verdict == IGNORED:  # 「忽略」不是质量判定, 不进误报率分母
            continue
        bucket = buckets[category]
        bucket["total"] += 1
        if verdict == FALSE_POSITIVE:
            bucket["false_positive"] += 1
            snippet = _attr(risk, "original_clause")
            if snippet:
                bucket["clauses"].append(snippet[:120])
        elif verdict == ACCEPTED:
            bucket["accepted"] += 1

    suggestions: list[dict[str, Any]] = []
    for category in sorted(buckets):
        bucket = buckets[category]
        total = bucket["total"]
        rate = round(bucket["false_positive"] / total, 4) if total else 0.0
        if total < min_samples or rate < fp_threshold:
            continue
        suggestions.append(
            {
                "category": category,
                "samples": total,
                "false_positives": bucket["false_positive"],
                "false_positive_rate": rate,
                "priority": "high" if rate >= 0.5 else "medium",
                "actions": [
                    "把误报原文加入 eval/goldens/contracts.json 作为「无风险」反例, 并纳入发布门禁回归",
                    f"在 Reviewer prompt 中为 {category} 增加明确排除条件与反例说明",
                    "收紧 risk_scoring 技能的命中条件, 要求同时出现法定构成要件",
                    "将置信度低于阈值的结论标记为「待人工复核」, 不再直接判为高危",
                    "用 build_eval_cases 导出的正例补充金标准, 复测 precision / recall",
                ],
                "sample_clauses": bucket["clauses"][:5],
            }
        )

    return {
        "min_samples": min_samples,
        "fp_threshold": fp_threshold,
        "categories_analyzed": len(buckets),
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
    }
