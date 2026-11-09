"""审查增强层持久化模型.

三张新表均由 ``SQLModel.metadata.create_all`` 在 lifespan 自动创建:
- ``contract_fact_items``: 合同要素核对表 (带原文定位与置信度)
- ``missing_clause_items``: 缺失/漏填条款清单
- ``risk_feedback``: 风险条目级反馈 (认可 / 误报 / 忽略), 供回归评测与采纳率统计
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.models.long_text import LongText

MEDIUM_TEXT = LongText()


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class ContractFactItem(SQLModel, table=True):
    """一行合同要素."""

    __tablename__ = "contract_fact_items"

    id: str = Field(default_factory=_uuid, primary_key=True)
    analysis_id: str = Field(foreign_key="analysis_results.id", index=True)
    key: str = Field(max_length=64, description="要素标识")
    label: str = Field(max_length=128, description="中文展示名")
    value: str = Field(
        default="",
        sa_column=Column("value", MEDIUM_TEXT, nullable=False, default=""),
    )
    evidence: str = Field(
        default="",
        sa_column=Column("evidence", MEDIUM_TEXT, nullable=False, default=""),
    )
    confidence: float = Field(default=0.0, description="抽取置信度")
    status: str = Field(default="missing", max_length=16, description="present / missing / unclear")
    required: bool = Field(default=False, description="是否法定必备条款")
    legal_basis: str = Field(
        default="",
        sa_column=Column("legal_basis", MEDIUM_TEXT, nullable=False, default=""),
    )
    order: int = Field(default=0, description="展示排序")


class MissingClauseItem(SQLModel, table=True):
    """一项检测到缺失的必备条款."""

    __tablename__ = "missing_clause_items"

    id: str = Field(default_factory=_uuid, primary_key=True)
    analysis_id: str = Field(foreign_key="analysis_results.id", index=True)
    key: str = Field(max_length=64)
    label: str = Field(max_length=128)
    reason: str = Field(
        default="",
        sa_column=Column("reason", MEDIUM_TEXT, nullable=False, default=""),
    )
    legal_basis: str = Field(
        default="",
        sa_column=Column("legal_basis", MEDIUM_TEXT, nullable=False, default=""),
    )
    suggested_text: str = Field(
        default="",
        sa_column=Column("suggested_text", MEDIUM_TEXT, nullable=False, default=""),
        description="建议补充的条款措辞 (可直接提给 HR)",
    )
    level: str = Field(default="medium", max_length=16)
    score: int = Field(default=30, ge=0, le=100)
    order: int = Field(default=0)


class RiskFeedback(SQLModel, table=True):
    """用户对单条 AI 风险结论的反馈, 是端到端评测集的来源."""

    __tablename__ = "risk_feedback"

    id: str = Field(default_factory=_uuid, primary_key=True)
    risk_item_id: str = Field(max_length=64, index=True, description="关联 risk_items.id")
    contract_id: str = Field(max_length=64, index=True)
    verdict: str = Field(
        max_length=32,
        description="accepted / false_positive / ignored",
    )
    comment: str = Field(
        default="",
        sa_column=Column("comment", MEDIUM_TEXT, nullable=False, default=""),
    )
    user_id: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
