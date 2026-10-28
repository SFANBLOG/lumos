"""企业审计查询接口（只读，供管理员合规核查）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from app.api.deps import DBSession, get_current_user
from app.models.audit import AuditEvent
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["🧾 合规审计"])


def _require_auditor(user: User = Depends(get_current_user)) -> User:
    if user.role not in {"owner", "admin", "auditor"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要审计权限")
    return user


@router.get("/events", summary="查询审计事件")
async def list_audit_events(session: DBSession, _user: User = Depends(_require_auditor), action: str | None = Query(default=None, max_length=80), page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    rows = (await session.execute(stmt.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"page": page, "page_size": page_size, "items": [{"id": i.id, "action": i.action, "resource_type": i.resource_type, "resource_id": i.resource_id, "actor_id": i.actor_id, "request_id": i.request_id, "ip_address": i.ip_address, "details": json.loads(i.details_json), "created_at": i.created_at} for i in rows]}
