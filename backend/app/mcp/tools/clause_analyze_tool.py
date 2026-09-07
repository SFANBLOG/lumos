"""
MCP 工具: 单条款深度分析.

对单条合同条款进行风险分类和法律关联分析。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.skills import get_skill


class ClauseAnalyzeTool:
    """条款深度分析 MCP 工具."""

    name = "clause_analyze"
    description = "对单条合同条款进行风险分类和法律关联分析"
    input_schema: dict = {
        "type": "object",
        "properties": {
            "clause_title": {"type": "string", "description": "条款标题/主题"},
            "clause_content": {"type": "string", "description": "条款原文内容"},
        },
        "required": ["clause_title", "clause_content"],
    }

    async def run(
        self,
        clause_title: str,
        clause_content: str,
    ) -> dict[str, Any]:
        logger.debug(f"[clause_analyze] title={clause_title!r}")
        legal_skill = get_skill("legal_analysis")
        analysis = await legal_skill.execute(
            clause_title=clause_title,
            clause_content=clause_content,
        )

        law_tool_results = []
        if analysis.get("primary_category"):
            from app.rag.vector_store import search_laws

            query = f"{clause_title} {clause_content[:200]}"
            law_tool_results = search_laws(
                query=query,
                n_results=3,
                category=analysis["primary_category"],
            )

        return {
            "clause_title": clause_title,
            "analysis": analysis,
            "related_laws": law_tool_results,
        }
