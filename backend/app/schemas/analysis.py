"""
风险分析结果相关 Schema.

定义 SSE 流式推送事件与最终分析报告的数据结构。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.analysis import RiskCategory, RiskLevel
from app.schemas.review import ContractFactResponse, MissingClauseResponse


# ─── SSE 事件类型 ──────────────────────────────────────────────


class SSEEventType(str, Enum):
    """SSE 流式推送事件类型."""

    # Agent 思考进度
    THINKING = "thinking"  # Agent 正在思考中 (附带当前步骤描述)
    NODE_START = "node_start"  # 某个 Node 开始执行
    NODE_COMPLETE = "node_complete"  # 某个 Node 执行完毕

    # 风险结果 (逐条推送)
    RISK_FOUND = "risk_found"  # 发现一条风险

    # 最终结果
    SUMMARY = "summary"  # 分析总结
    COMPLETE = "complete"  # 全部完成
    ERROR = "error"  # 发生错误


class SSEEvent(BaseModel):
    """SSE 事件基础结构."""

    event: SSEEventType
    data: dict = Field(default_factory=dict)


# ─── 风险条目 ──────────────────────────────────────────────────


class RiskItemResponse(BaseModel):
    """单项风险条目响应."""

    id: str = Field(default="", description="风险条目 ID, 提交风险反馈时使用")
    category: RiskCategory
    level: RiskLevel
    title: str = Field(description="风险标题 (说人话)")
    original_clause: str = Field(default="", description="原始合同条文")
    explanation: str = Field(description="大白话解读")
    legal_basis: str = Field(default="", description="法律依据")
    negotiation_tip: str = Field(default="", description="谈判话术建议")
    suggested_revision: str = Field(
        default="",
        description="条款级修改建议 (redline): 这一条应改成什么文本",
    )
    score: int = Field(ge=0, le=100, description="单项评分")

    model_config = {"from_attributes": True}


# ─── 完整报告 ──────────────────────────────────────────────────


class AnalysisReportResponse(BaseModel):
    """完整风险分析报告响应."""

    contract_id: str
    overall_score: int = Field(ge=0, le=100, description="合同安全总评分")
    overall_level: RiskLevel
    summary: str = Field(description="一句话总结")
    risk_items: list[RiskItemResponse] = Field(
        default_factory=list,
        description="逐条风险清单 (按危险程度排序)",
    )
    contract_facts: list[ContractFactResponse] = Field(
        default_factory=list,
        description="合同要素核对表 (带原文定位与置信度)",
    )
    missing_clauses: list[MissingClauseResponse] = Field(
        default_factory=list,
        description="缺失/漏填的法定必备条款与应有保护条款",
    )
    coverage_score: int = Field(
        default=100,
        ge=0,
        le=100,
        description="必备条款覆盖率, 独立于 overall_score 与 confidence_score",
    )
    content_notice: str | None = Field(
        default=None,
        description="内容提示 (提交内容被判定为疑似非合同时给出, 供报告顶部标注)",
    )
    analyzed_at: datetime

    model_config = {"from_attributes": True}


# ─── Agent 节点进度 ────────────────────────────────────────────


class AgentNodeProgress(BaseModel):
    """Agent 节点执行进度."""

    node_name: str = Field(description="当前执行节点名称")
    description: str = Field(description="节点功能描述")
    progress: float = Field(ge=0, le=1, description="进度百分比 (0~1)")
