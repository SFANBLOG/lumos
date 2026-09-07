"""
法律分析技能.

提供条款分类、法条匹配、法律推理能力。
"""

from __future__ import annotations

from typing import Any

from app.skills.base import BaseSkill

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "non_compete": ["竞业", "竞业限制", "竞业禁止", "同业"],
    "probation_salary": ["试用期工资", "试用期薪资", "试用期报酬"],
    "probation_insurance": ["试用期社保", "试用期保险", "试用期内不缴纳"],
    "salary_deduction": ["扣薪", "罚款", "扣除工资", "绩效扣"],
    "job_description": ["岗位职责", "工作内容", "岗位调整", "调岗"],
    "obedience_clause": ["服从安排", "无条件", "必须服从", "绝对服从"],
    "resignation": ["辞职", "离职", "提前通知", "解除劳动"],
    "leave_rights": ["年假", "休假", "病假", "事假", "带薪"],
    "jurisdiction": ["仲裁", "管辖", "争议解决", "诉讼地"],
    "training_bond": ["培训费", "服务期", "培训协议", "违约金"],
}


class LegalAnalysisSkill(BaseSkill):
    """条款分类 + 法条关联."""

    name = "legal_analysis"
    description = "对合同条款进行风险分类并关联相关法律条文"

    async def execute(self, *, clause_title: str, clause_content: str, **kwargs: Any) -> dict[str, Any]:
        combined = f"{clause_title} {clause_content}"
        matched_categories: list[str] = []

        for category, keywords in _CATEGORY_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                matched_categories.append(category)

        return {
            "categories": matched_categories,
            "primary_category": matched_categories[0] if matched_categories else None,
            "confidence": len(matched_categories) > 0,
        }
