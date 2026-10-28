"""审计服务。敏感正文、密码和令牌一律不得写入审计详情。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


async def record_audit_event(session: AsyncSession, *, action: str, resource_type: str, resource_id: str | None = None, actor_id: str | None = None, request_id: str | None = None, ip_address: str | None = None, details: dict[str, Any] | None = None) -> None:
    """添加一条最小化审计事件，由调用方所在事务统一提交。"""
    session.add(AuditEvent(action=action, resource_type=resource_type, resource_id=resource_id, actor_id=actor_id, request_id=request_id, ip_address=ip_address, details_json=json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))))
