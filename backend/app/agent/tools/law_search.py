"""
法律条文检索工具 (兼容层).

委托给 MCP law_search 工具执行实际检索。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.mcp.client import MCPClient


async def search_labor_law(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """检索劳动法相关条文 (通过 MCP 工具)."""
    logger.debug(f"🔎 法律检索 | query={query!r} | top_k={top_k}")
    mcp = MCPClient()
    result = await mcp.call("law_search", query=query, top_k=top_k)
    return result.get("results", [])
