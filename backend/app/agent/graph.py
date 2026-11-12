"""
多智能体协作式合同审查工作流 (LangGraph).

默认 ``AGENT_MODE=multi``: 多个自治智能体通过共享消息总线协作,
由 Coordinator 动态编排, Verifier 独立复核并可否决结论、发起返工::

    START → coordinator → extractor → retriever → reviewer → verifier
                                          ↑                    │
                                          └──── rework ────────┘
                                                             ↓
                                                       negotiator → END

- Coordinator 依合同规模决定参与智能体 (agent_plan), 并逐个下发 task 消息;
- 每个智能体执行完广播 result 消息, 审查轨迹全部落在 agent_messages;
- reviewer 之后由条件边按 agent_plan 决定是否进入独立复核;
- Verifier 交叉核验原文定位与法条溯源, 不通过则给 Reviewer 发 rework 消息,
  条件边把流程退回 Reviewer 重审 (受 max_review_rounds 限制, 默认 1 轮);
- 通过 (或达上限) 则给 Negotiator 发 handoff 消息放行。

``AGENT_MODE=linear`` 保留原四节点线性流水线作为回退 (回归对比 / 降级用)。

对外保持 ``run_contract_analysis`` 接口、SSE 事件协议、报告结构与
fail-loud 语义不变: NODE_START 现在由各节点自行推送, runner 只负责回放,
因此线性与多智能体两种拓扑都能维持「开始 → 思考 → 完成」的事件时间线。
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import BaseAgent
from app.agent.state import AgentMessage, AgentState
from app.agent.sub_agents.coordinator_agent import CoordinatorAgent
from app.agent.sub_agents.extractor_agent import ExtractorAgent
from app.agent.sub_agents.negotiator_agent import NegotiatorAgent
from app.agent.sub_agents.retriever_agent import RetrieverAgent
from app.agent.sub_agents.reviewer_agent import ReviewerAgent
from app.agent.sub_agents.verifier_agent import VerifierAgent
from app.models.analysis import AnalysisResult, RiskItem
from app.models.contract import Contract
from app.models.review import ContractFactItem, MissingClauseItem
from app.schemas.analysis import AgentNodeProgress, SSEEvent, SSEEventType

#: 旧版线性流水线 (回退模式)
_LINEAR_SEQ: list[tuple[str, str]] = [
    ("extractor", "📝 结构化抽取 — 正在整理合同条款…"),
    ("retriever", "⚖️ 法规检索 — 正在查询相关劳动法条文…"),
    ("reviewer", "🔍 风险审查 — 正在评估风险并核验依据…"),
    ("negotiator", "🗣️ 运营与谈判 — 正在整理义务并生成话术…"),
]

#: 多智能体协作链路 (默认模式)
_MULTI_SEQ: list[tuple[str, str]] = [
    ("coordinator", "🧭 协调调度 — 正在分派审查任务…"),
    ("extractor", "📝 结构化抽取 — 正在整理合同条款…"),
    ("retriever", "⚖️ 法规检索 — 正在查询相关劳动法条文…"),
    ("reviewer", "🔍 风险审查 — 正在评估风险并核验依据…"),
    ("verifier", "🧪 独立复核 — 正在交叉验证依据与结论…"),
    ("negotiator", "🗣️ 运营与谈判 — 正在整理义务并生成话术…"),
]

_AGENTS: dict[str, BaseAgent] = {
    a.name: a
    for a in [
        CoordinatorAgent(),
        ExtractorAgent(),
        RetrieverAgent(),
        ReviewerAgent(),
        VerifierAgent(),
        NegotiatorAgent(),
    ]
}

#: 关键节点: 一旦执行失败, 风险结论即失去依据 (条款没抽出来 / 没真正审过),
#: 此时必须显式失败, 不能再用「0 风险 / 已完成」冒充审查通过
_CRITICAL_NODES: frozenset[str] = frozenset({"extractor", "reviewer"})


def _current_mode() -> str:
    """当前编排模式: multi (默认) / linear (回退)."""
    mode = os.getenv("AGENT_MODE", "multi").strip().lower()
    return mode if mode in ("multi", "linear") else "multi"


def _field(state: Any, key: str, default: Any) -> Any:
    """条件边兼容 dict / AgentState 两种状态载体."""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _node_action(agent: BaseAgent, idx: int, total: int) -> Any:
    """构造 LangGraph 节点动作.

    每个节点 = 一个自治智能体: 先推 NODE_START, 执行智能体, 广播 result 消息,
    再追加 NODE_COMPLETE (reviewer 追加 RISK_FOUND)。事件按序累积进
    ``state.events``, 由 ``run_contract_analysis`` 沿 SSE 协议回放。
    """

    async def action(state: AgentState) -> dict[str, Any]:
        events: list[SSEEvent] = [
            SSEEvent(
                event=SSEEventType.NODE_START,
                data=AgentNodeProgress(
                    node_name=agent.name,
                    description=agent.description,
                    progress=idx / total,
                ).model_dump(),
            )
        ]

        prev_error_len = len(state.errors)
        state = await agent(state)  # BaseAgent.__call__: 捕获异常写入 errors
        state.agent_trace.append(agent.name)
        state.agent_messages.append(
            AgentMessage(
                sender=agent.name,
                recipient="broadcast",
                kind="result",
                content=f"{agent.description.split('—')[0].strip()} 已完成",
                round=state.review_rounds,
            )
        )

        if len(state.errors) > prev_error_len:
            if agent.name in _CRITICAL_NODES:
                # 关键节点失败: 标记降级, 全图结束后不再产出「已完成」报告
                state.ai_degraded = True
            events.append(
                SSEEvent(
                    event=SSEEventType.THINKING,
                    data={"message": f"⚠️ {state.errors[-1]}，继续处理…"},
                )
            )
        events.append(
            SSEEvent(
                event=SSEEventType.NODE_COMPLETE,
                data=AgentNodeProgress(
                    node_name=agent.name,
                    description=f"{agent.description.split('—')[0].strip()} ✅ 完成",
                    progress=(idx + 1) / total,
                ).model_dump(),
            )
        )
        if agent.name == "reviewer":
            for assessment in state.risk_assessments:
                events.append(
                    SSEEvent(
                        event=SSEEventType.RISK_FOUND,
                        data=assessment.model_dump(),
                    )
                )

        return {
            **state.model_dump(exclude={"events"}),
            "events": [*state.events, *events],
        }

    return action


def _route_after_review(state: Any) -> str:
    """条件边: Coordinator 未编排 verifier 时直接放行到谈判."""
    plan = _field(state, "agent_plan", [])
    return "verifier" if "verifier" in plan else "negotiator"


def _route_after_verify(state: Any) -> str:
    """条件边: Verifier 否决且未达返工上限 → 退回 Reviewer 重审."""
    verdict = _field(state, "verdict", "")
    rounds = _field(state, "review_rounds", 0)
    max_rounds = _field(state, "max_review_rounds", 1)
    return "rework" if verdict == "rework" and rounds <= max_rounds else "approve"


@lru_cache
def build_contract_graph(mode: str = "multi") -> Any:
    """构建并编译 LangGraph 合同审查图 (按模式进程级缓存)."""
    if mode not in ("multi", "linear"):
        mode = "multi"
    seq = _MULTI_SEQ if mode == "multi" else _LINEAR_SEQ
    total = len(seq)

    graph = StateGraph(AgentState)
    for idx, (name, _description) in enumerate(seq):
        graph.add_node(name, _node_action(_AGENTS[name], idx, total))

    graph.add_edge(START, seq[0][0])

    if mode == "linear":
        for i in range(total - 1):
            graph.add_edge(seq[i][0], seq[i + 1][0])
        graph.add_edge(seq[-1][0], END)
    else:
        graph.add_edge("coordinator", "extractor")
        graph.add_edge("extractor", "retriever")
        graph.add_edge("retriever", "reviewer")
        graph.add_conditional_edges(
            "reviewer",
            _route_after_review,
            {"verifier": "verifier", "negotiator": "negotiator"},
        )
        graph.add_conditional_edges(
            "verifier",
            _route_after_verify,
            {"rework": "reviewer", "approve": "negotiator"},
        )
        graph.add_edge("negotiator", END)

    compiled = graph.compile()
    logger.info(
        f"🕸️ LangGraph 工作流就绪 | 模式: {mode} | 节点: {[n for n, _ in seq]}"
    )
    return compiled


async def run_contract_analysis(
    contract_id: str,
    raw_text: str,
    session: AsyncSession | None = None,
    contract_type: str = "",
) -> AsyncGenerator[SSEEvent, None]:
    """
    执行 LangGraph 合同分析工作流, 异步生成 SSE 事件流.

    - 以 ``graph.astream`` 逐节点推进并回放节点事件;
    - NODE_START 由各节点自行推送, runner 只回放, 兼容线性/多智能体拓扑;
    - 全图结束后持久化结果并推送 SUMMARY / COMPLETE。
    """
    mode = _current_mode()
    logger.info(
        f"🚀 Agent 工作流启动 (LangGraph/{mode}) | 合同ID: {contract_id}"
    )

    graph = build_contract_graph(mode)
    initial = AgentState(
        contract_id=contract_id,
        raw_text=raw_text,
        contract_type=contract_type,
    )

    final_state = initial
    emitted = 0
    try:
        async for raw in graph.astream(initial, stream_mode="values"):
            if emitted == 0 and raw == initial.model_dump():
                continue  # astream 首项为初始状态快照
            state = AgentState(**raw)
            final_state = state

            # 回放本节点新产生的事件 (NODE_START/THINKING/NODE_COMPLETE/RISK_FOUND)
            if len(state.events) > emitted:
                for event in state.events[emitted:]:
                    yield event
                emitted = len(state.events)
    except Exception as e:
        logger.exception(f"❌ LangGraph 工作流异常 | 合同ID: {contract_id}")
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": f"分析引擎异常: {e}"},
        )
        return

    # AI 不可用 / 关键节点失败导致降级: 不产出「已完成」报告, 直接报错,
    # 避免把未完成的审查当成「低风险 / 0 问题」的合规结论 (假阴性)
    if final_state.ai_degraded:
        logger.error(f"⚠️ AI 审查未完成 (降级) | 合同ID: {contract_id}")
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={
                "message": "本次审查未能完成：AI 深度分析不可用或审查引擎异常"
                "（常见原因：API Key 无效、额度不足、网络故障）。"
                "请检查大模型配置后重新审查，切勿据此放行合同。"
            },
        )
        return

    content_notice: str | None = None
    if session is not None:
        content_notice = await _persist(final_state, session)

    yield SSEEvent(
        event=SSEEventType.SUMMARY,
        data={
            "overall_score": final_state.overall_score,
            "overall_level": final_state.overall_level.value,
            "summary": final_state.summary,
            "total_clauses": len(final_state.extracted_clauses),
            "total_risks": len(final_state.risk_assessments),
            "legal_references_count": len(final_state.legal_references),
            "confidence_score": final_state.confidence_score,
            "quality_issues": final_state.quality_issues,
            "contract_facts": final_state.contract_facts,
            # 审查增强层: 统一转成纯 dict, 兼容 SSE 侧的 json.dumps 序列化
            "contract_fact_items": [f.model_dump() for f in final_state.contract_fact_items],
            "missing_clauses": [m.model_dump() for m in final_state.missing_clauses],
            "coverage_score": final_state.coverage_score,
            "contract_type": final_state.contract_type,
            "agent_mode": mode,
            "agent_trace": final_state.agent_trace,
            "review_rounds": final_state.review_rounds,
            # 内容提示: 提交内容被判定为疑似非合同时非空, 前端据此在报告顶部标注
            "content_notice": content_notice,
        },
    )

    yield SSEEvent(
        event=SSEEventType.COMPLETE,
        data={"message": "✨ 合同风险排查完成！"},
    )

    logger.info(
        f"🏁 LangGraph 工作流完成 | 合同ID: {contract_id} | 模式: {mode} | "
        f"评分: {final_state.overall_score}/100 | 风险: {len(final_state.risk_assessments)} 项"
    )


async def _persist(state: AgentState, session: AsyncSession) -> str | None:
    """将分析结果与风险条目持久化到数据库.

    Returns:
        内容提示文案 (提交内容被判定为疑似非合同时), 无提示时为 None.
    """
    try:
        # 内容体检结论在提交时已落库, 这里读回来给报告加顶部标注:
        # 非合同内容也允许 force 继续, 但结论必须明确告知"仅供参考".
        contract = await session.get(Contract, state.contract_id)
        notice = contract.doc_check_note if contract is not None else None
        summary = f"【内容提示】{notice}\n\n{state.summary}" if notice else state.summary

        analysis = AnalysisResult(
            contract_id=state.contract_id,
            overall_score=state.overall_score,
            overall_level=state.overall_level,
            summary=summary,
        )
        session.add(analysis)
        await session.flush()

        for idx, assessment in enumerate(state.risk_assessments):
            session.add(
                RiskItem(
                    analysis_id=analysis.id,
                    category=assessment.category,
                    level=assessment.level,
                    title=assessment.title,
                    original_clause=assessment.original_clause,
                    explanation=assessment.explanation,
                    legal_basis=assessment.legal_basis,
                    negotiation_tip=assessment.negotiation_tip,
                    suggested_revision=assessment.suggested_revision,
                    revision_reason=assessment.revision_reason,
                    revision_diff=assessment.revision_diff,
                    revision_method=assessment.revision_method,
                    revision_confidence=assessment.revision_confidence,
                    score=assessment.score,
                    order=idx,
                )
            )

        # 审查增强层: 要素核对表与缺失条款清单随报告一起落库
        for idx, fact in enumerate(state.contract_fact_items):
            session.add(
                ContractFactItem(
                    analysis_id=analysis.id,
                    key=fact.key,
                    label=fact.label,
                    value=fact.value,
                    evidence=fact.evidence,
                    confidence=fact.confidence,
                    status=fact.status,
                    required=fact.required,
                    legal_basis=fact.legal_basis,
                    matched_by=fact.matched_by,
                    contradiction=fact.contradiction,
                    rule_set=fact.rule_set,
                    order=idx,
                )
            )
        for idx, clause in enumerate(state.missing_clauses):
            session.add(
                MissingClauseItem(
                    analysis_id=analysis.id,
                    key=clause.key,
                    label=clause.label,
                    reason=clause.reason,
                    legal_basis=clause.legal_basis,
                    suggested_text=clause.suggested_text,
                    level=clause.level,
                    score=clause.score,
                    order=idx,
                )
            )

        await session.commit()
        logger.info(
            f"💾 结果已持久化 | 合同ID: {state.contract_id} | "
            f"风险: {len(state.risk_assessments)} 条"
        )
        return notice
    except Exception as e:
        logger.error(f"💾 持久化失败: {e}")
        await session.rollback()
        return None
