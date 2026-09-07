"""
MCP 服务端.

注册所有工具并通过 MCP 协议暴露给外部调用方。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.mcp.tools.clause_analyze_tool import ClauseAnalyzeTool
from app.mcp.tools.law_search_tool import LawSearchTool
from app.mcp.tools.negotiation_tool import NegotiationTool
from app.mcp.tools.risk_assess_tool import RiskAssessTool


class LumosMCPServer:
    """Lumos MCP 服务端，管理并调度所有注册的工具."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for tool_cls in [LawSearchTool, ClauseAnalyzeTool, RiskAssessTool, NegotiationTool]:
            tool = tool_cls()
            self._tools[tool.name] = tool
        logger.info(f"MCP 服务端已初始化 | 注册工具: {list(self._tools)}")

    def list_tools(self) -> list[dict[str, str]]:
        """列出所有可用工具的描述."""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """调用指定工具."""
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"MCP 工具不存在: {tool_name}，可用: {list(self._tools)}")
        logger.debug(f"MCP 调用工具: {tool_name} | 参数: {list(arguments)}")
        return await tool.run(**arguments)


_mcp_server: LumosMCPServer | None = None


def get_mcp_server() -> LumosMCPServer:
    """获取全局 MCP 服务端单例."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = LumosMCPServer()
    return _mcp_server
