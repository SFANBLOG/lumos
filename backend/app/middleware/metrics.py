"""
性能指标中间件.

统计请求计数、延迟分布，暴露 /metrics 端点供监控使用。
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class MetricsMiddleware(BaseHTTPMiddleware):
    """收集请求级性能指标."""

    def __init__(self, app):
        super().__init__(app)
        self.request_count: int = 0
        self.status_counts: dict[int, int] = defaultdict(int)
        self.total_latency_ms: float = 0.0

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path == "/metrics":
            return JSONResponse(self._snapshot())

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.request_count += 1
        self.status_counts[response.status_code] += 1
        self.total_latency_ms += elapsed_ms

        return response

    def _snapshot(self) -> dict:
        avg = (
            self.total_latency_ms / self.request_count
            if self.request_count
            else 0.0
        )
        return {
            "request_count": self.request_count,
            "avg_latency_ms": round(avg, 2),
            "status_codes": dict(self.status_counts),
        }
