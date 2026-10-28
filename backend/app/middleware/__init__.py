"""
中间件模块.

提供请求级别的横切关注点: 日志、限流、异常处理、性能指标。
"""

from __future__ import annotations

from fastapi import FastAPI

from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware


def register_middleware(app: FastAPI) -> None:
    """按顺序注册所有中间件 (后注册的先执行)."""
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
