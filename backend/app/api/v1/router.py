"""
API v1 路由聚合.

将所有 v1 版本的子路由统一注册在此。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.audit import router as audit_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.playbooks import router as playbooks_router
from app.api.v1.consult import router as consult_router
from app.api.v1.contracts import router as contracts_router
from app.api.v1.health import router as health_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.mcp_routes import router as mcp_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(health_router)
v1_router.include_router(auth_router)
v1_router.include_router(audit_router)
v1_router.include_router(approvals_router)
v1_router.include_router(playbooks_router)
v1_router.include_router(contracts_router)
v1_router.include_router(mcp_router)
v1_router.include_router(ingest_router)
v1_router.include_router(consult_router)
