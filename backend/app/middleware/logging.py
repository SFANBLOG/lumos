"""
请求日志中间件.

为每个请求生成唯一 X-Request-ID，记录方法、路径、状态码和耗时。
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from loguru import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的关键信息."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed_ms:.1f}ms"

        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} "
            f"({elapsed_ms:.1f}ms) [rid={request_id[:8]}]"
        )

        return response
