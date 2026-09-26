"""
LangGraph 合同审查工作流.

以 LangGraph ``StateGraph`` 编排 6 个阶段节点:

    extract → retrieve → review → quality_gate → obligation → negotiate

节点间共享 pydantic ``AgentState``; 每个节点包装一个子智能体执行,
节点内产生的事件 (THINKING / NODE_COMPLETE / RISK_FOUND) 按序累积进
``state.events``, 由 ``run_contract_analysis`` 沿 SSE 协议回放;
NODE_START 事件由 runner 按线性图顺序预推, 保持原有 SSE 时间线语义。

对外保持 ``run_contract_analysis`` 接口不变 (供 SSE 流式调用)。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import BaseAgent
from app.agent.state import AgentState
from app.agent.sub_agents.extractor_agent import ExtractorAgent
from app.agent.sub_agents.negotiator_agent import NegotiatorAgent
from app.agent.sub_agents.retriever_agent import RetrieverAgent
from app.agent.sub_agents.reviewer_agent import ReviewerAgent
from app.agent.sub_agents.quality_gate_agent import QualityGateAgent
from app.agent.sub_agents.obligation_agent import ObligationAgent
from app.models.analysis import AnalysisResult, RiskItem
from app.schemas.analysis import AgentNodeProgress, SSEEvent, SSEEventType

#: 工作流节点序列 (线性链, 顺序即执行顺序)
_NODE_SEQ: list[tuple[str, str]] = [
    ("extractor", "📝 结构化抽取 — 正在整理合同条款…"),
    ("retriever", "⚖️ 法规检索 — 正在查询相关劳动法条文…"),
    ("reviewer", "🔍 风险审查 — 正在逐项评估风险…"),
    ("quality_gate", "✅ 证据质检 — 正在核验风险依据…"),
    ("obligation", "📅 合同运营 — 正在提取期限与义务…"),
    ("negotiator", "🗣️ 谈判策略 — 正在生成沟通话术…"),
]

_AGENTS: dict[str, BaseAgent] = {
    a.name: a
    for a in [
        ExtractorAgent(),
        RetrieverAgent(),
        ReviewerAgent(),
        QualityGateAgent(),
        ObligationAgent(),
        NegotiatorAgent(),
    ]
}


def _node_action(agent: BaseAgent, idx: int, total: int) -> Any:
    """构造 LangGraph 节点动作.

    执行对应子智能体, 将本轮节点事件 (错误提示/完成/风险逐条) 追加到
    ``state.events`` 后返回全量状态更新; NODE_START 由 runner 按图预推。
    """
    async def action(state: AgentState) -> dict[str, Any]:
        prev_error_len = len(state.errors)
        state = await agent(state)  # BaseAgent.__call__: 捕获异常写入 errors
        state.agent_trace.append(agent.name)

        events: list[SSEEvent] = []
        if len(state.errors) > prev_error_len:
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
                    description=f"{agent.description.split('—')[0]}✅ 完成",
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


@lru_cache
def build_contract_graph() -> Any:
    """构建并编译 LangGraph 合同审查图 (进程级缓存)."""
    total = len(_NODE_SEQ)
    graph = StateGraph(AgentState)
    for idx, (name, _description) in enumerate(_NODE_SEQ):
        graph.add_node(name, _node_action(_AGENTS[name], idx, total))

    graph.add_edge(START, _NODE_SEQ[0][0])
    for i in range(total - 1):
        graph.add_edge(_NODE_SEQ[i][0], _NODE_SEQ[i + 1][0])
    graph.add_edge(_NODE_SEQ[-1][0], END)

    compiled = graph.compile()
    logger.info(
        f"🕸️ LangGraph 工作流就绪 | 节点: {[n for n, _ in _NODE_SEQ]}"
    )
    return compiled


def _start_event(idx: int, total: int) -> SSEEvent:
    """构造 NODE_START 事件 (runner 按线性图顺序推送)."""
    name, description = _NODE_SEQ[idx]
    return SSEEvent(
        event=SSEEventType.NODE_START,
        data=AgentNodeProgress(
            node_name=name,
            description=description,
            progress=idx / total,
        ).model_dump(),
    )


async def run_contract_analysis(
    contract_id: str,
    raw_text: str,
    session: AsyncSession | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """
    执行 LangGraph 合同分析工作流, 异步生成 SSE 事件流.

    - 以 ``graph.astream`` 逐节点推进并回放节点事件;
    - NODE_START 按图顺序预推, 保持「节点开始 → 思考 → 完成」时间线;
    - 全图结束后持久化结果并推送 SUMMARY / COMPLETE。
    """
    logger.info(f"🚀 Agent 工作流启动 (LangGraph) | 合同ID: {contract_id}")

    graph = build_contract_graph()
    initial = AgentState(contract_id=contract_id, raw_text=raw_text)
    total = len(_NODE_SEQ)

    # 预推首个节点 START, 让前端立即展示第一阶段
    yield _start_event(0, total)

    final_state = initial
    emitted = 0
    completed = 0
    try:
        async for raw in graph.astream(initial, stream_mode="values"):
            if completed == 0 and emitted == 0 and raw == initial.model_dump():
                continue  # astream 首项为初始状态快照
            state = AgentState(**raw)
            final_state = state
            completed += 1

            # 回放本节点新产生的事件 (THINKING/NODE_COMPLETE/RISK_FOUND)
            if len(state.events) > emitted:
                for event in state.events[emitted:]:
                    yield event
                emitted = len(state.events)

            # 线性链: 还有后继节点则预推其 NODE_START
            if completed < total:
                yield _start_event(completed, total)
    except Exception as e:
        logger.exception(f"❌ LangGraph 工作流异常 | 合同ID: {contract_id}")
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": f"分析引擎异常: {e}"},
        )
        return

    if session is not None:
        await _persist(final_state, session)

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
        },
    )

    yield SSEEvent(
        event=SSEEventType.COMPLETE,
        data={"message": "✨ 合同风险排查完成！"},
    )

    logger.info(
        f"🏁 LangGraph 工作流完成 | 合同ID: {contract_id} | "
        f"评分: {final_state.overall_score}/100 | 风险: {len(final_state.risk_assessments)} 项"
    )


async def _persist(state: AgentState, session: AsyncSession) -> None:
    """将分析结果与风险条目持久化到数据库."""
    try:
        analysis = AnalysisResult(
            contract_id=state.contract_id,
            overall_score=state.overall_score,
            overall_level=state.overall_level,
            summary=state.summary,
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
                    score=assessment.score,
                    order=idx,
                )
            )

        await session.commit()
        logger.info(
            f"💾 结果已持久化 | 合同ID: {state.contract_id} | "
            f"风险: {len(state.risk_assessments)} 条"
        )
    except Exception as e:
        logger.error(f"💾 持久化失败: {e}")
        await session.rollback()
