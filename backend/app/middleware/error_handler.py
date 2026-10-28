"""
全局异常处理中间件.

捕获未处理异常，返回统一格式的错误响应。
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from loguru import logger


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """捕获异常并返回统一 JSON 错误格式."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", "unknown")
            logger.exception(
                f"未处理异常 | path={request.url.path} [rid={request_id[:8]}]"
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "服务内部错误，请稍后重试",
                    "request_id": request_id,
                },
            )
