"""
MCP 工具: 法律条文语义检索.

通过向量数据库检索最相关的劳动法条文。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.models.analysis import RiskCategory
from app.rag.vector_store import search_laws

_CATEGORY_VALUES = [c.value for c in RiskCategory]


class LawSearchTool:
    """法律条文语义检索 MCP 工具."""

    name = "law_search"
    description = "根据查询文本语义检索最相关的中国劳动法条文"
    input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询文本"},
            "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
            "category": {
                "type": "string",
                "enum": _CATEGORY_VALUES,
                "description": "风险分类过滤 (可选)",
            },
        },
        "required": ["query"],
    }

    async def run(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> dict[str, Any]:
        logger.debug(f"[law_search] query={query!r} top_k={top_k}")
        results = search_laws(query=query, n_results=top_k, category=category)
        return {
            "query": query,
            "results": results,
            "total": len(results),
        }
