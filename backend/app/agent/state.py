"""
Agent 状态定义.

定义 LangGraph 流转过程中的统一状态结构，
每个节点读取并更新此状态，形成完整的思考链路。

多智能体模式下, ``agent_messages`` 是智能体之间的显式消息总线:
Coordinator 下发任务 (task/plan), 各智能体广播结果 (result),
Verifier 发送复核结论 (rework/handoff), 图中的条件边据此动态路由。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.analysis import RiskCategory, RiskLevel
from app.schemas.analysis import SSEEvent


# ─── 结构化合同条款 ────────────────────────────────────────────


class ExtractedClause(BaseModel):
    """经 AI 结构化提取后的单条合同条款."""

    clause_index: int = Field(description="条款序号")
    title: str = Field(description="条款标题 (如: 竞业限制)")
    content: str = Field(description="条款原文内容")
    category: RiskCategory | None = Field(
        default=None,
        description="关联的风险分类 (可能为空)",
    )


# ─── 法规检索结果 ──────────────────────────────────────────────


class LegalReference(BaseModel):
    """RAG 检索到的法律条文."""

    law_name: str = Field(description="法律名称 (如: 《劳动合同法》)")
    article: str = Field(description="条款编号 (如: 第二十三条)")
    content: str = Field(description="法条原文")
    relevance_score: float = Field(ge=0, le=1, description="相关性评分")


# ─── 风险评估结果 ──────────────────────────────────────────────


class RiskAssessment(BaseModel):
    """单项风险评估."""

    category: RiskCategory
    level: RiskLevel
    title: str = Field(description="风险标题 (说人话)")
    original_clause: str = Field(description="原始合同条文")
    explanation: str = Field(description="大白话解读")
    legal_basis: str = Field(description="法律依据")
    negotiation_tip: str = Field(description="谈判话术建议")
    score: int = Field(ge=0, le=100, description="单项评分 (100=安全)")


# ─── 智能体间消息 ──────────────────────────────────────────────


class AgentMessage(BaseModel):
    """一条智能体间消息 (消息总线).

    ``kind``: plan / task / result / rework / verdict / handoff
    ``recipient``: 具体智能体名, 或 "broadcast" 表示全员广播.
    """

    sender: str = Field(description="发送方智能体")
    recipient: str = Field(description="接收方智能体或 broadcast")
    kind: str = Field(description="消息类型")
    content: str = Field(default="", description="消息内容 / 决策依据")
    round: int = Field(default=0, ge=0, description="所属审查轮次")


# ─── LangGraph 全局状态 ────────────────────────────────────────


class AgentState(BaseModel):
    """
    LangGraph 工作流的全局状态.

    每个智能体读取需要的字段，处理后更新对应字段，
    状态就像流水线上的「工单」，沿着 Graph 逐步被充实完整。
    """

    # ── 输入 ──
    contract_id: str = Field(description="合同 ID")
    raw_text: str = Field(description="脱敏后的合同原文")

    # ── Node A: 结构化提取 ──
    corrected_text: str = Field(default="", description="纠错后的文本")
    extracted_clauses: list[ExtractedClause] = Field(
        default_factory=list,
        description="结构化提取的条款列表",
    )

    # ── Node B: 法规检索 (RAG) ──
    legal_references: list[LegalReference] = Field(
        default_factory=list,
        description="检索到的相关法条",
    )

    # ── Node C: 风险审查 (含证据质检) ──
    risk_assessments: list[RiskAssessment] = Field(
        default_factory=list,
        description="逐项风险评估结果",
    )
    overall_score: int = Field(default=0, ge=0, le=100, description="整体评分")
    overall_level: RiskLevel = Field(
        default=RiskLevel.MEDIUM,
        description="整体风险等级",
    )
    summary: str = Field(default="", description="一句话总结")
    confidence_score: int = Field(default=100, ge=0, le=100, description="证据完整性置信度")
    quality_issues: list[str] = Field(default_factory=list, description="待人工复核项")

    # ── Node D: 义务提取与谈判话术 ──
    contract_facts: dict = Field(default_factory=dict, description="合同运营要素与义务")

    # ── 流程控制 ──
    current_node: str = Field(default="", description="当前执行的节点名称")
    errors: list[str] = Field(default_factory=list, description="错误信息收集")
    # AI 大模型不可用 (Key 无效/额度不足/网络故障) 时置 True:
    # 上层据此拒绝产出「已完成/低风险」报告, 避免把未完成的审查误报为安全
    ai_degraded: bool = Field(default=False, description="AI 模型不可用导致审查降级")
    agent_trace: list[str] = Field(
        default_factory=list,
        description="已执行的子智能体名称列表 (执行轨迹, 含返工重复执行)",
    )

    # ── 多智能体协作 ──
    agent_messages: list[AgentMessage] = Field(
        default_factory=list,
        description="智能体间消息总线 (任务分派 / 结果广播 / 复核返工 / 交接)",
    )
    agent_plan: list[str] = Field(
        default_factory=list,
        description="Coordinator 动态编排的参与智能体清单",
    )
    verdict: str = Field(default="", description="Verifier 结论: rework / approve")
    review_rounds: int = Field(default=0, ge=0, description="已发起的返工轮次")
    max_review_rounds: int = Field(
        default=1, ge=0, le=3, description="允许的返工上限, 防止无限循环"
    )

    # LangGraph 节点执行期间产生的事件 (NODE_START/THINKING/NODE_COMPLETE/RISK_FOUND),
    # 由 run_contract_analysis 回放为 SSE 帧
    events: list[SSEEvent] = Field(
        default_factory=list,
        description="工作流事件累积 (供 SSE 回放与测试断言)",
    )
