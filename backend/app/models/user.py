"""
用户模型.

定义用户表结构和认证相关的 Pydantic DTO。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    """企业工作区中的最小 RBAC 角色集。"""

    OWNER = "owner"
    ADMIN = "admin"
    AUDITOR = "auditor"
    MEMBER = "member"


class User(SQLModel, table=True):
    """用户表."""

    __tablename__ = "users"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="用户唯一标识",
    )
    username: str = Field(index=True, unique=True, description="用户名")
    email: str = Field(index=True, unique=True, description="邮箱")
    hashed_password: str = Field(description="哈希后的密码")
    is_active: bool = Field(default=True, description="是否激活")
    role: UserRole = Field(default=UserRole.MEMBER, index=True, description="工作区角色")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="创建时间",
    )
