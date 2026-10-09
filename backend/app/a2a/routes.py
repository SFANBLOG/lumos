"""
Lumos A2A 路由.

暴露 A2A 协议端点:
- ``GET  /.well-known/agent.json``  -> Agent Card (自描述能力)
- ``POST /a2a``                     -> JSON-RPC (message/send, tasks/get…)
- ``POST /a2a/stream``              -> SSE 流式 JSON-RPC (message/stream)

兼容新旧两套方法名 (message/* 与 tasks/*), 便于对接不同版本 A2A 客户端。
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from app.a2a.agent_card import get_agent_card
from app.a2a.executor import LumosAgentExecutor
from app.a2a.models import (
    A2AErrorCode,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    TaskSendParams,
)

router = APIRouter(tags=["🤝 A2A"])

_executor = LumosAgentExecutor()


def _err(code: int, message: str, req_id: int | str | None = None, data: object = None) -> dict:
    return JSONRPCResponse(
        id=req_id, error=JSONRPCError(code=code, message=message, data=data)
    ).model_dump(exclude_none=True)


def _resolve_ids(params: TaskSendParams) -> tuple[str, str]:
    task_id = params.id or f"a2a-{uuid.uuid4().hex}"
    context_id = params.contextId or f"ctx-{uuid.uuid4().hex}"
    return task_id, context_id


@router.get("/.well-known/agent.json")
async def agent_card() -> JSONResponse:
    """A2A Agent Card —— 供其他 Agent 发现 Lumos 能力."""
    card = get_agent_card()
    return JSONResponse(card.model_dump(exclude_none=True))


@router.post("/a2a")
async def a2a_rpc(request: Request) -> JSONResponse:
    """A2A JSON-RPC 同步端点."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(_err(A2AErrorCode.PARSE_ERROR, "Invalid JSON"), status_code=400)

    try:
        req = JSONRPCRequest(**payload)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            _err(A2AErrorCode.INVALID_REQUEST, f"Invalid request: {e}"), status_code=400
        )

    method = req.method
    params = req.params or {}

    # ── 同步发送 (支持 message/send 与旧版 tasks/send) ──
    if method in ("message/send", "tasks/send"):
        try:
            send_params = TaskSendParams(**params)
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                _err(A2AErrorCode.INVALID_PARAMS, f"Invalid params: {e}", req.id),
                status_code=422,
            )
        task_id, context_id = _resolve_ids(send_params)
        task = await _executor.execute_task(task_id, context_id, send_params.message)
        return JSONResponse(
            JSONRPCResponse(id=req.id, result=task.model_dump(exclude_none=True)).model_dump(
                exclude_none=True
            )
        )

    # ── 查询任务状态 (message/get 与 tasks/get) ──
    if method in ("message/get", "tasks/get"):
        task_id = params.get("id")
        if not task_id:
            return JSONResponse(
                _err(A2AErrorCode.INVALID_PARAMS, "Missing task id", req.id), status_code=422
            )
        # 当前实现为无状态同步执行, 任务完成后结果不长期保留; 返回 unknown 提示。
        return JSONResponse(
            _err(
                A2AErrorCode.INVALID_PARAMS,
                "Lumos A2A 为无状态同步执行, 请使用 message/send 或 message/stream 获取结果。",
                req.id,
                data={"taskId": task_id},
            ),
            status_code=404,
        )

    # ── 取消 (message/cancel 与 tasks/cancel) ──
    if method in ("message/cancel", "tasks/cancel"):
        return JSONResponse(
            _err(
                A2AErrorCode.INVALID_PARAMS,
                "Lumos A2A 暂不支持任务取消 (同步执行, 提交即运行)。",
                req.id,
            ),
            status_code=405,
        )

    return JSONResponse(
        _err(A2AErrorCode.METHOD_NOT_FOUND, f"Method not found: {method}", req.id),
        status_code=404,
    )


@router.post("/a2a/stream")
async def a2a_stream(request: Request) -> StreamingResponse:
    """A2A SSE 流式端点 (message/stream / tasks/sendSubscribe)."""
    try:
        payload = await request.json()
        req = JSONRPCRequest(**payload)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"A2A stream 非法请求: {e}")

        async def _err_gen():
            body = json.dumps(
                _err(A2AErrorCode.INVALID_REQUEST, f"Invalid request: {e}"), ensure_ascii=False
            )
            yield f"data: {body}\n\n"

        return StreamingResponse(_err_gen(), media_type="text/event-stream")

    method = req.method
    if method not in ("message/stream", "tasks/sendSubscribe"):
        async def _unsupported():
            body = json.dumps(
                _err(A2AErrorCode.METHOD_NOT_FOUND, f"Method not found: {method}", req.id),
                ensure_ascii=False,
            )
            yield f"data: {body}\n\n"

        return StreamingResponse(_unsupported(), media_type="text/event-stream")

    try:
        send_params = TaskSendParams(**(req.params or {}))
    except Exception as e:  # noqa: BLE001
        async def _badparams():
            body = json.dumps(
                _err(A2AErrorCode.INVALID_PARAMS, f"Invalid params: {e}", req.id),
                ensure_ascii=False,
            )
            yield f"data: {body}\n\n"

        return StreamingResponse(_badparams(), media_type="text/event-stream")

    task_id, context_id = _resolve_ids(send_params)

    async def event_gen():
        async for update in _executor.stream_task(task_id, context_id, send_params.message):
            envelope = JSONRPCResponse(
                id=req.id, result=update.model_dump(exclude_none=True)
            ).model_dump(exclude_none=True)
            yield f"data: {json.dumps(envelope, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
