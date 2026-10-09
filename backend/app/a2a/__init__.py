"""
Lumos A2A (Agent2Agent Protocol) 集成模块.

把 Lumos 合同审查引擎暴露为标准 A2A Agent, 供其他 Agent 通过
Agent Card 发现并调用。详见 :mod:`app.a2a.routes` 端点定义。
"""

from __future__ import annotations

from app.a2a.agent_card import get_agent_card
from app.a2a.executor import LumosAgentExecutor
from app.a2a.routes import router

__all__ = ["router", "get_agent_card", "LumosAgentExecutor"]
