"""
技能系统.

提供可复用的能力模块，供子智能体按需注册和调用。
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.legal_analysis import LegalAnalysisSkill
from app.skills.negotiation import NegotiationSkill
from app.skills.risk_scoring import RiskScoringSkill
from app.skills.text_preprocessing import TextPreprocessingSkill

_SKILL_REGISTRY: dict[str, type[BaseSkill]] = {
    "text_preprocessing": TextPreprocessingSkill,
    "legal_analysis": LegalAnalysisSkill,
    "risk_scoring": RiskScoringSkill,
    "negotiation": NegotiationSkill,
}


def get_skill(name: str) -> BaseSkill:
    """按名称获取技能实例."""
    cls = _SKILL_REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"未知技能: {name}，可用: {list(_SKILL_REGISTRY)}")
    return cls()


def list_skills() -> list[str]:
    """列出所有已注册技能名称."""
    return list(_SKILL_REGISTRY)
