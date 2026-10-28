from __future__ import annotations
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import select
from app.api.deps import DBSession, get_current_user
from app.models.approval import ApprovalStatus, ApprovalTask
from app.models.contract import Contract
from app.models.user import User
from app.services.audit import record_audit_event
router=APIRouter(prefix="/approvals", tags=["✅ 审批协作"])
class Decision(BaseModel): status: ApprovalStatus; comment: str=Field(default="",max_length=1000)


@router.get("")
async def queue(
    session: DBSession,
    user: User = Depends(get_current_user),
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
):
    """返回当前用户可处理或可跟踪的审批队列，并附带最小合同上下文。"""
    stmt = select(ApprovalTask).order_by(ApprovalTask.created_at.desc())
    if status_filter:
        stmt = stmt.where(ApprovalTask.status == status_filter)
    if user.role.value not in {"owner", "admin", "auditor"}:
        stmt = stmt.where(ApprovalTask.requester_id == user.id)

    tasks = (await session.execute(stmt)).scalars().all()
    result = []
    for task in tasks:
        contract = await session.get(Contract, task.contract_id)
        result.append({
            "id": task.id,
            "contract_id": task.contract_id,
            "status": task.status,
            "comment": task.comment,
            "created_at": task.created_at,
            "decided_at": task.decided_at,
            "can_decide": user.role.value in {"owner", "admin", "auditor"},
            "contract_preview": (contract.raw_text or "")[:120] if contract else "合同已不存在",
            "contract_status": contract.status if contract else None,
        })
    return result
@router.post("/contracts/{contract_id}", status_code=201)
async def create(contract_id:str, session:DBSession, user:User=Depends(get_current_user)):
    if not await session.get(Contract,contract_id): raise HTTPException(404,"合同不存在")
    task=ApprovalTask(contract_id=contract_id,requester_id=user.id);session.add(task);await record_audit_event(session,action="approval.created",resource_type="contract",resource_id=contract_id,actor_id=user.id);await session.commit();await session.refresh(task);return task
@router.post("/{task_id}/decision")
async def decide(task_id:str, body:Decision, session:DBSession, user:User=Depends(get_current_user)):
    if user.role.value not in {"owner","admin","auditor"}: raise HTTPException(status.HTTP_403_FORBIDDEN,"需要审批权限")
    task=await session.get(ApprovalTask,task_id)
    if not task or task.status!=ApprovalStatus.PENDING: raise HTTPException(409,"审批任务不存在或已处理")
    task.status=body.status;task.comment=body.comment;task.reviewer_id=user.id;task.decided_at=datetime.now(UTC);session.add(task);await record_audit_event(session,action=f"approval.{body.status.value}",resource_type="contract",resource_id=task.contract_id,actor_id=user.id);await session.commit();return task
@router.get("/contracts/{contract_id}")
async def list_tasks(contract_id:str,session:DBSession,user:User=Depends(get_current_user)):
    return (await session.execute(select(ApprovalTask).where(ApprovalTask.contract_id==contract_id).order_by(ApprovalTask.created_at.desc()))).scalars().all()
