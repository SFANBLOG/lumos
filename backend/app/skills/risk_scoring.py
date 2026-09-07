"""
风险评分技能.

提供评分算法、等级判定、趋势分析能力。
"""

from __future__ import annotations

from typing import Any

from app.skills.base import BaseSkill

_LEVEL_THRESHOLDS = [
    (30, "high"),
    (50, "medium"),
    (70, "low"),
    (100, "safe"),
]

_RISK_SIGNALS: dict[str, int] = {
    "non_compete": -15,
    "probation_salary": -10,
    "probation_insurance": -20,
    "salary_deduction": -15,
    "obedience_clause": -10,
    "resignation": -10,
    "training_bond": -10,
    "jurisdiction": -5,
    "job_description": -5,
    "leave_rights": -5,
}


class RiskScoringSkill(BaseSkill):
    """基于条款分类和数量计算合同安全评分."""

    name = "risk_scoring"
    description = "根据条款风险分类和数量计算整体安全评分"

    async def execute(
        self,
        *,
        categories: list[str],
        total_clauses: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        base_score = 100
        for cat in categories:
            base_score += _RISK_SIGNALS.get(cat, 0)

        score = max(0, min(100, base_score))

        level = "safe"
        for threshold, lvl in _LEVEL_THRESHOLDS:
            if score <= threshold:
                level = lvl
                break

        risk_ratio = len(categories) / max(total_clauses, 1)

        return {
            "score": score,
            "level": level,
            "risk_ratio": round(risk_ratio, 2),
            "risk_count": len(categories),
        }
