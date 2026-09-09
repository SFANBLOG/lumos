"""
智能咨询会话数据模型.

存储用户与法律顾问 AI 的多轮问答会话与消息记录。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlmodel import Field, SQLModel

MEDIUM_TEXT = MEDIUMTEXT()


class ConsultSession(SQLModel, table=True):
    """一次咨询会话 (归属某个用户, 可选关联一份分析报告)."""

    __tablename__ = "consult_sessions"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )

    # ---- 归属 ----
    user_id: str = Field(foreign_key="users.id", index=True, description="归属用户 ID")

    # ---- 会话信息 ----
    title: str = Field(default="新对话", max_length=60, description="会话标题")
    contract_id: str | None = Field(
        default=None,
        foreign_key="contracts.id",
        index=True,
        description="关联分析报告 ID (可空)",
    )

    # ---- 时间 ----
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="创建时间",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="最后活跃时间",
    )


class ConsultMessage(SQLModel, table=True):
    """会话内单条消息."""

    __tablename__ = "consult_messages"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )

    # ---- 关联 ----
    session_id: str = Field(
        foreign_key="consult_sessions.id",
        index=True,
        description="关联会话 ID",
    )

    # ---- 内容 ----
    seq: int = Field(default=0, description="会话内序号 (按此排序)")
    role: str = Field(description="角色: user | assistant")
    content: str = Field(
        sa_column=Column("content", MEDIUM_TEXT, nullable=False),
        description="问题原文或回答全文",
    )
    refs_json: str = Field(
        default="",
        sa_column=Column("refs_json", MEDIUM_TEXT, nullable=False),
        description="助手消息: 法条引用列表 JSON",
    )
    suggestions_json: str = Field(
        default="",
        sa_column=Column("suggestions_json", MEDIUM_TEXT, nullable=False),
        description="助手消息: 追问建议列表 JSON",
    )

    # ---- 时间 ----
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="消息时间",
    )
