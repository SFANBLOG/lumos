"""
MCP 工具路由.

提供 MCP 工具的查询和调用接口 (带参数 schema 校验)。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import AuthAny
from app.mcp.server import get_mcp_server

router = APIRouter(prefix="/mcp", tags=["🔧 MCP 工具"])


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}


@router.get(
    "/tools",
    summary="列出所有 MCP 工具 (含参数 schema)",
)
async def list_tools(_auth: AuthAny) -> list[dict[str, Any]]:
    server = get_mcp_server()
    return server.list_tools()


@router.post(
    "/tools/call",
    summary="调用 MCP 工具",
)
async def call_tool(req: ToolCallRequest, _auth: AuthAny) -> Any:
    server = get_mcp_server()
    tool = server.get_tool(req.tool_name)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP 工具不存在: {req.tool_name}",
        )

    schema = getattr(tool, "input_schema", {}) or {}
    errors = _validate_args(req.arguments, schema)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=errors,
        )
    return await server.call_tool(req.tool_name, req.arguments)


def _validate_args(arguments: dict[str, Any], schema: dict) -> dict[str, str]:
    """按 input_schema 校验参数, 返回 {field: 原因}."""
    errors: dict[str, str] = {}
    if not isinstance(arguments, dict):
        return {"arguments": "参数必须是 JSON 对象"}

    raw_props = schema.get("properties")
    props: dict = raw_props if isinstance(raw_props, dict) else {}
    required: list[str] = schema.get("required") or []

    for name in required:
        if name not in arguments or arguments[name] is None:
            errors[name] = "缺少必填参数"

    for name, value in arguments.items():
        if name not in props:
            errors[name] = "未知参数"
            continue
        spec = props[name]
        expected = spec.get("type")
        if value is None:
            if name not in required:
                continue
            errors[name] = "参数不能为 null"
            continue

        if expected == "string":
            if not isinstance(value, str):
                errors[name] = "应为字符串"
            elif spec.get("enum") and value not in spec["enum"]:
                errors[name] = f"取值必须是 {spec['enum']} 之一"
        elif expected == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                errors[name] = "应为整数"
            elif spec.get("minimum") is not None and value < spec["minimum"]:
                errors[name] = f"不能小于 {spec['minimum']}"
            elif spec.get("maximum") is not None and value > spec["maximum"]:
                errors[name] = f"不能大于 {spec['maximum']}"
        elif expected == "array":
            if not isinstance(value, list):
                errors[name] = "应为数组"
                continue
            if spec.get("minItems") is not None and len(value) < spec["minItems"]:
                errors[name] = f"至少 {spec['minItems']} 项"
            item_spec = spec.get("items") or {}
            if item_spec.get("enum"):
                bad = [v for v in value if v not in item_spec["enum"]]
                if bad:
                    errors[name] = f"包含非法取值: {bad}"
    return errors
