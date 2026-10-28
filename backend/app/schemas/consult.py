"""
智能咨询相关 Schema.

定义 /consult 接口的请求/响应结构与 SSE 事件协议。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ConsultEventType(str, Enum):
    """咨询 SSE 事件类型."""

    SESSION = "session"  # 会话已建立/复用 (data: {session_id})
    STEP = "step"  # 思考步骤 (data: {message})
    ANSWER = "answer"  # 完整回答 (data: {message_id, content, references, suggestions})
    COMPLETE = "complete"  # 本轮完成 (data: {message})
    ERROR = "error"  # 出错 (data: {message})


class ConsultAskRequest(BaseModel):
    """发起一轮咨询提问."""

    question: str = Field(min_length=2, max_length=2000, description="问题内容")
    session_id: str | None = Field(default=None, description="会话 ID (空则新建)")
    contract_id: str | None = Field(default=None, description="关联分析报告 ID (可空)")


class ConsultSessionOut(BaseModel):
    """会话列表项."""

    id: str
    title: str
    contract_id: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ConsultMessageOut(BaseModel):
    """会话内消息 (历史记录)."""

    id: str
    role: str
    content: str
    references: list[dict] | None = None
    suggestions: list[str] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsultSessionListResponse(BaseModel):
    """会话分页列表."""

    total: int
    page: int
    page_size: int
    items: list[ConsultSessionOut]
