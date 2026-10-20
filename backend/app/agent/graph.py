"""
LangGraph 合同审查工作流.

以 LangGraph ``StateGraph`` 编排 4 个阶段节点:

    extractor → retriever → reviewer → negotiator

其中证据质检 (quality_gate) 内联在 reviewer 节点内执行, 合同义务提取
(obligation) 内联在 negotiator 节点内执行; 节点间共享 pydantic
``AgentState``; 每个节点包装一个子智能体执行, 节点内产生的事件
(THINKING / NODE_COMPLETE / RISK_FOUND) 按序累积进 ``state.events``,
由 ``run_contract_analysis`` 沿 SSE 协议回放; NODE_START 事件由
runner 按线性图顺序预推, 保持原有 SSE 时间线语义。

对外保持 ``run_contract_analysis`` 接口不变 (供 SSE 流式调用)。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import BaseAgent
from app.agent.state import AgentState
from app.agent.sub_agents.extractor_agent import ExtractorAgent
from app.agent.sub_agents.negotiator_agent import NegotiatorAgent
from app.agent.sub_agents.retriever_agent import RetrieverAgent
from app.agent.sub_agents.reviewer_agent import ReviewerAgent
from app.models.analysis import AnalysisResult, RiskItem, RiskLevel
from app.models.contract import Contract, ContractStatus
from app.models.approval import ApprovalTask
from app.schemas.analysis import AgentNodeProgress, SSEEvent, SSEEventType

#: 工作流节点序列 (线性链, 顺序即执行顺序)
_NODE_SEQ: list[tuple[str, str]] = [
    ("extractor", "📝 结构化抽取 — 正在整理合同条款…"),
    ("retriever", "⚖️ 法规检索 — 正在查询相关劳动法条文…"),
    ("reviewer", "🔍 风险审查 — 正在评估风险并核验依据…"),
    ("negotiator", "🗣️ 运营与谈判 — 正在整理义务并生成话术…"),
]

_AGENTS: dict[str, BaseAgent] = {
    a.name: a
    for a in [
        ExtractorAgent(),
        RetrieverAgent(),
        ReviewerAgent(),
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


def _review_gate(state: AgentState) -> dict[str, Any]:
    """人工介入闸门: 高风险或含待复核项时 ``interrupt()`` 挂起, 否则放行至 END.

    ``interrupt`` 会暂停图执行并把状态落盘 (checkpointer); 审批通过后以相同
    ``thread_id`` 续跑至此节点, ``interrupt()`` 立即返回, 节点返回空更新使图走到 END。
    """
    needs_review = bool(state.quality_issues) or state.overall_level == RiskLevel.HIGH
    if needs_review:
        interrupt(
            {
                "contract_id": state.contract_id,
                "overall_level": state.overall_level.value,
                "risk_count": len(state.risk_assessments),
                "quality_issues": state.quality_issues,
                "message": "⏸️ 存在待人工复核项或高风险，流程已挂起等待审批",
            }
        )
    return {}


@lru_cache
def build_contract_graph() -> Any:
    """构建并编译 LangGraph 合同审查图 (进程级缓存).

    接入 checkpointer 后支持中断续跑/重放: 高风险或含待复核项的合同会在
    ``review_gate`` 节点被 ``interrupt()`` 挂起, 状态落盘 (Postgres/Memory),
    审批通过后用同一 ``thread_id`` 续跑至 END。
    """
    total = len(_NODE_SEQ)
    graph = StateGraph(AgentState)
    for idx, (name, _description) in enumerate(_NODE_SEQ):
        graph.add_node(name, _node_action(_AGENTS[name], idx, total))

    # 人工介入闸门: 分析完成后判断是否需要挂起等待审批
    graph.add_node("review_gate", _review_gate)
    graph.add_edge(START, _NODE_SEQ[0][0])
    for i in range(total - 1):
        graph.add_edge(_NODE_SEQ[i][0], _NODE_SEQ[i + 1][0])
    graph.add_edge(_NODE_SEQ[-1][0], "review_gate")
    graph.add_edge("review_gate", END)

    compiled = graph.compile(checkpointer=get_checkpointer())
    logger.info(
        f"🕸️ LangGraph 工作流就绪 | 节点: {[n for n, _ in _NODE_SEQ] + ['review_gate']}"
    )
    return compiled


def get_checkpointer() -> Any:
    """按配置返回 LangGraph checkpointer (Postgres 持久化 / Memory 进程内).

    后端由 ``checkpoint_backend`` 决定; Postgres 基于 psycopg 的 AsyncPostgresSaver
    (LangGraph 官方实现), 缺依赖或 memory 模式时回退 MemorySaver, 保证无 Postgres
    环境 (如单测) 仍可运行。
    """
    from app.core.config import get_settings

    backend = getattr(get_settings(), "checkpoint_backend", "postgres")
    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        return AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_postgres_dsn)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ Postgres checkpointer 不可用, 回退 MemorySaver: {e}")
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()


async def setup_checkpointer() -> None:
    """异步建表 (仅 Postgres 需要; MemorySaver 无 setup). 由 lifespan 启动时调用."""
    cp = get_checkpointer()
    setup = getattr(cp, "setup", None)
    if setup is not None:
        await setup()


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
    config = {"configurable": {"thread_id": contract_id}}
    initial = AgentState(contract_id=contract_id, raw_text=raw_text)
    total = len(_NODE_SEQ)

    # 预推首个节点 START, 让前端立即展示第一阶段
    yield _start_event(0, total)

    final_state = initial
    emitted = 0
    completed = 0
    try:
        async for raw in graph.astream(initial, config=config, stream_mode="values"):
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

    # 图是否已中断挂起 (review_gate 触发 interrupt, next 非空即暂停等待审批)
    snap = await graph.aget_state(config)
    if snap.next:
        final_state = AgentState(**snap.values)
        if session is not None:
            await _save_snapshot_and_create_approval(contract_id, final_state, session)
        reasons = list(final_state.quality_issues)
        if final_state.overall_level == RiskLevel.HIGH:
            reasons.append(f"整体风险等级: {final_state.overall_level.value}")
        yield SSEEvent(
            event=SSEEventType.AWAITING_REVIEW,
            data={
                "contract_id": contract_id,
                "quality_issues": final_state.quality_issues,
                "overall_level": final_state.overall_level.value,
                "risk_count": len(final_state.risk_assessments),
                "reasons": reasons,
                "message": "⏸️ 存在待人工复核项或高风险，流程已挂起等待审批",
            },
        )
        return

    # 正常完成 (无中断): 落库并发布
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


async def _save_snapshot_and_create_approval(
    contract_id: str, state: AgentState, session: AsyncSession
) -> None:
    """流程挂起: 落库中间状态快照 + 自动创建审批任务."""
    snapshot = state.model_dump(exclude={"events"})
    contract = await session.get(Contract, contract_id)
    if contract is not None:
        contract.analysis_snapshot = json.dumps(snapshot, ensure_ascii=False, default=str)
        contract.status = ContractStatus.AWAITING_REVIEW
        contract.updated_at = datetime.now(UTC)
        session.add(contract)
    task = ApprovalTask(
        contract_id=contract_id,
        requester_id=contract.requester_id if contract else None,
    )
    session.add(task)
    await session.commit()
    logger.info(
        f"⏸️ 流程挂起等待人工审批 | 合同ID: {contract_id} | 待复核项: {state.quality_issues}"
    )


async def resume_contract_analysis(
    contract_id: str,
    session: AsyncSession | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """审批通过后从 checkpoint 续跑至 END 并发布 (LangGraph 原生 resume).

    与首跑共享同一 ``thread_id``; 图从中断点 (review_gate 的 ``interrupt`` 之后)
    继续, 回到 END 后落库并推送 SUMMARY/COMPLETE。无需再从 JSON 快照重建状态。
    """
    graph = build_contract_graph()
    config = {"configurable": {"thread_id": contract_id}}
    try:
        raw = await graph.ainvoke(None, config=config)
    except Exception as e:
        logger.exception(f"❌ LangGraph 续跑异常 | 合同ID: {contract_id}")
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": f"续跑失败: {e}"},
        )
        return

    state = AgentState(**raw)
    if session is not None:
        await _persist(state, session)
        contract = await session.get(Contract, contract_id)
        if contract is not None:
            contract.status = ContractStatus.COMPLETED
            contract.analysis_snapshot = None  # 已发布, 清空挂起快照
            contract.updated_at = datetime.now(UTC)
            session.add(contract)
            await session.commit()

    yield SSEEvent(
        event=SSEEventType.SUMMARY,
        data={
            "overall_score": state.overall_score,
            "overall_level": state.overall_level.value,
            "summary": state.summary,
            "total_clauses": len(state.extracted_clauses),
            "total_risks": len(state.risk_assessments),
            "legal_references_count": len(state.legal_references),
            "confidence_score": state.confidence_score,
            "quality_issues": state.quality_issues,
            "contract_facts": state.contract_facts,
        },
    )
    yield SSEEvent(
        event=SSEEventType.COMPLETE,
        data={"message": "✨ 合同风险排查完成！"},
    )
