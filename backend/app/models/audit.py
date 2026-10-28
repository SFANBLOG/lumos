"""企业审计事件模型：保存关键数据操作的可追溯记录。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.models.long_text import LongText


class AuditEvent(SQLModel, table=True):
    """仅追加的审计记录；业务代码不得更新或删除该表记录。"""

    __tablename__ = "audit_events"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    action: str = Field(index=True, max_length=80)
    resource_type: str = Field(index=True, max_length=80)
    resource_id: str | None = Field(default=None, index=True, max_length=64)
    actor_id: str | None = Field(default=None, index=True, max_length=64)
    request_id: str | None = Field(default=None, index=True, max_length=64)
    ip_address: str | None = Field(default=None, max_length=64)
    details_json: str = Field(default="{}", sa_column=Column(LongText(), nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
