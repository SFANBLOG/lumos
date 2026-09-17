"""审查 Playbook 的可见配置接口。"""
from fastapi import APIRouter, Depends

from app.agent.playbooks import DEFAULT_PLAYBOOK
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/playbooks", tags=["📘 审查标准"])


@router.get("/active")
async def active_playbook(_user: User = Depends(get_current_user)):
    """返回当前工作区启用的审查基线；后续可接入工作区自定义版本。"""
    return {**DEFAULT_PLAYBOOK, "version": "baseline-1.0", "status": "active"}
