"""
Agent 状态定义.

定义 LangGraph 流转过程中的统一状态结构，
每个节点读取并更新此状态，形成完整的思考链路。

多智能体模式下, ``agent_messages`` 是智能体之间的显式消息总线:
Coordinator 下发任务 (task/plan), 各智能体广播结果 (result),
Verifier 发送复核结论 (rework/handoff), 图中的条件边据此动态路由。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from app.agent.reducers import (
    append_errors,
    append_events,
    append_messages,
    append_trace,
)
from app.models.analysis import RiskCategory, RiskLevel
from app.schemas.analysis import SSEEvent
from app.schemas.review import ContractFact, MissingClause


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
    suggested_revision: str = Field(
        default="",
        description="条款级修改建议 (redline): 这一条应改成什么文本",
    )
    # redline v2: LLM 逐条改写 (由 Reviewer 解析) 与最终可审计的改写结果
    llm_revised_clause: str = Field(default="", description="LLM 给出的逐条改写文本")
    llm_rewrite_reason: str = Field(default="", description="LLM 给出的改写理由")
    revision_reason: str = Field(default="", description="最终采用的改写理由")
    revision_diff: str = Field(default="", description="原条款 → 建议条款的 unified diff")
    revision_method: str = Field(default="", description="llm / rule, 标记改写来源")
    revision_confidence: float = Field(default=0.0, ge=0, le=1)
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
    contract_type: str = Field(
        default="",
        description="合同类型: labor_contract / service_contract / nda; 空或 auto 时按原文推断",
    )

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
    # 旧字段保留给 SSE / 前端做兼容消费 (日期、金额、义务关键词、自动续约)
    contract_facts: dict = Field(default_factory=dict, description="合同运营要素与义务")
    # 审查增强层: 结构化要素表、缺失条款、必备条款覆盖率
    contract_fact_items: list[ContractFact] = Field(
        default_factory=list,
        description="合同要素核对表 (带原文定位与置信度)",
    )
    missing_clauses: list[MissingClause] = Field(
        default_factory=list,
        description="缺失的法定必备条款与应有保护条款",
    )
    coverage_score: int = Field(
        default=100,
        ge=0,
        le=100,
        description="必备条款覆盖率, 与 overall_score / confidence_score 相互独立",
    )

    # ── 流程控制 ──
    current_node: str = Field(default="", description="当前执行的节点名称")
    # 以下四个字段带追加归并器: 节点只返回本次新增条目, 由 LangGraph 累加,
    # 返工 / 多节点写同一字段时不会互相覆盖, 也不会重复累加。
    errors: Annotated[list[str], append_errors] = Field(
        default_factory=list, description="错误信息收集"
    )
    # AI 大模型不可用 (Key 无效/额度不足/网络故障) 时置 True:
    # 上层据此拒绝产出「已完成/低风险」报告, 避免把未完成的审查误报为安全
    ai_degraded: bool = Field(default=False, description="AI 模型不可用导致审查降级")
    agent_trace: Annotated[list[str], append_trace] = Field(
        default_factory=list,
        description="已执行的子智能体名称列表 (执行轨迹, 含返工重复执行)",
    )
    review_decision: str = Field(default="", description="人工复核门结论: approved / rejected")
    # 累计产生的事件总数: 单调游标, 不受 events 窗口裁剪影响, SSE 回放依赖它
    event_count: int = Field(default=0, ge=0, description="累计产生的 SSE 事件数")
    # 长期记忆召回的审查提示 (由 Reviewer 参考, 不含合同原文)
    memory_hints: list[str] = Field(
        default_factory=list, description="跨任务记忆召回的审查提示"
    )

    # ── 多智能体协作 ──
    agent_messages: Annotated[list[AgentMessage], append_messages] = Field(
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
    # 由 run_contract_analysis 回放为 SSE 帧; 追加归并器保证跨节点 / 跨返工不丢事件
    events: Annotated[list[SSEEvent], append_events] = Field(
        default_factory=list,
        description="工作流事件累积 (供 SSE 回放与测试断言)",
    )
