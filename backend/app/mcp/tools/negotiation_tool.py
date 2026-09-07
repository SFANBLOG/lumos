"""
MCP 工具: 谈判话术生成.

根据风险条款类型生成专业的谈判话术。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.skills import get_skill


class NegotiationTool:
    """谈判话术生成 MCP 工具."""

    name = "negotiation"
    description = "根据风险条款类型生成可直接发送给 HR 的谈判话术"

    async def run(
        self,
        category: str | None = None,
    ) -> dict[str, Any]:
        logger.debug(f"[negotiation] category={category}")
        negotiation_skill = get_skill("negotiation")
        result = await negotiation_skill.execute(category=category)
        return result
