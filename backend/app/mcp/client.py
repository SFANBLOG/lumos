"""
MCP 客户端封装.

供子智能体通过统一接口调用 MCP 工具。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.mcp.server import get_mcp_server


class MCPClient:
    """子智能体调用 MCP 工具的客户端."""

    async def call(self, tool_name: str, **arguments: Any) -> Any:
        """调用一个 MCP 工具并返回结果."""
        server = get_mcp_server()
        try:
            result = await server.call_tool(tool_name, arguments)
            logger.debug(f"MCP 调用成功: {tool_name}")
            return result
        except Exception as e:
            logger.error(f"MCP 调用失败: {tool_name} → {e}")
            raise
