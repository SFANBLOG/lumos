"""
MCP 工具路由.

提供 MCP 工具的查询和调用接口。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import AuthAny
from app.mcp.server import get_mcp_server

router = APIRouter(prefix="/mcp", tags=["🔧 MCP 工具"])


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}


@router.get(
    "/tools",
    summary="列出所有 MCP 工具",
)
async def list_tools(_auth: AuthAny) -> list[dict[str, str]]:
    server = get_mcp_server()
    return server.list_tools()


@router.post(
    "/tools/call",
    summary="调用 MCP 工具",
)
async def call_tool(req: ToolCallRequest, _auth: AuthAny) -> Any:
    server = get_mcp_server()
    return await server.call_tool(req.tool_name, req.arguments)
