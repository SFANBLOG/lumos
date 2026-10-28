"""
MCP 工具: 风险评分.

根据条款的风险分类列表计算合同安全评分。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.models.analysis import RiskCategory
from app.skills import get_skill

_CATEGORY_VALUES = [c.value for c in RiskCategory]


class RiskAssessTool:
    """风险评分 MCP 工具."""

    name = "risk_assess"
    description = "根据条款风险分类计算合同整体安全评分"
    input_schema: dict = {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": _CATEGORY_VALUES},
                "minItems": 1,
                "description": "检测到的风险分类列表",
            },
            "total_clauses": {
                "type": "integer",
                "minimum": 1,
                "description": "合同总条款数",
            },
        },
        "required": ["categories", "total_clauses"],
    }

    async def run(
        self,
        categories: list[str],
        total_clauses: int,
    ) -> dict[str, Any]:
        logger.debug(f"[risk_assess] categories={categories} total={total_clauses}")
        scoring_skill = get_skill("risk_scoring")
        result = await scoring_skill.execute(
            categories=categories,
            total_clauses=total_clauses,
        )
        return result
