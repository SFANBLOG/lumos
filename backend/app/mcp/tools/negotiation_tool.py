"""
MCP 工具: 谈判话术生成.

根据风险条款类型生成专业的谈判话术。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.models.analysis import RiskCategory
from app.skills import get_skill

_CATEGORY_VALUES = [c.value for c in RiskCategory]


class NegotiationTool:
    """谈判话术生成 MCP 工具."""

    name = "negotiation"
    description = "根据风险条款类型生成可直接发送给 HR 的谈判话术"
    input_schema: dict = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": _CATEGORY_VALUES,
                "description": "风险分类 (不选则生成通用话术)",
            },
        },
        "required": [],
    }

    async def run(
        self,
        category: str | None = None,
    ) -> dict[str, Any]:
        logger.debug(f"[negotiation] category={category}")
        negotiation_skill = get_skill("negotiation")
        result = await negotiation_skill.execute(category=category)
        return result
