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

状态: 累积字段 (errors / agent_trace / agent_messages / events) 走追加归并器,
节点只返回本次新增条目; 结论型字段 (条款 / 法条 / 风险) 仍是覆盖语义。
检查点: 编译时注入 checkpointer, 以 contract_id 为 thread_id 逐节点落快照,
提供状态查询、历史列举与 resume_contract_analysis 断点续跑。
记忆管理: 工作记忆按窗口裁剪 (``event_count`` 游标保证 SSE 不丢帧),
短期记忆由 ``app.agent.memory`` 按 TTL / 容量清理, 长期记忆经
``build_recall`` 注入 ``memory_hints``、完成后由 ``record_experience`` 沉淀。
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import BaseAgent
from app.agent.checkpoint import get_checkpointer, graph_config
from app.agent.memory import build_recall, record_experience
from app.agent.reducers import state_delta
from app.agent.state import AgentMessage, AgentState
from app.agent.sub_agents.coordinator_agent import CoordinatorAgent
from app.agent.sub_agents.extractor_agent import ExtractorAgent
from app.agent.sub_agents.negotiator_agent import NegotiatorAgent
from app.agent.sub_agents.retriever_agent import RetrieverAgent
from app.agent.sub_agents.reviewer_agent import ReviewerAgent
from app.agent.sub_agents.verifier_agent import VerifierAgent
from app.core.config import get_settings
from app.models.analysis import AnalysisResult, RiskItem, RiskLevel
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

#: 人工复核门节点 (CHECKPOINT_REVIEW_GATE=true 且启用检查点时才插入拓扑)
_REVIEW_GATE = "review_gate"


def _current_mode() -> str:
    """当前编排模式: multi (默认) / linear (回退)."""
    mode = os.getenv("AGENT_MODE", "multi").strip().lower()
    return mode if mode in ("multi", "linear") else "multi"


def _field(state: Any, key: str, default: Any) -> Any:
    """条件边兼容 dict / AgentState 两种状态载体."""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _review_gate_enabled() -> bool:
    """复核门依赖真实 checkpointer, backend=off 时自动降级为直通."""
    return bool(get_settings().checkpoint_review_gate and get_checkpointer() is not None)


def _pending_interrupt(snapshot: Any) -> dict[str, Any] | None:
    """读取 StateSnapshot 中待处理的 interrupt (人工复核请求), 无挂起时返回 None."""
    for task in getattr(snapshot, "tasks", ()) or ():
        for item in getattr(task, "interrupts", ()) or ():
            value = getattr(item, "value", None)
            return {
                "node": str(getattr(task, "name", _REVIEW_GATE)),
                "payload": value if isinstance(value, dict) else {"value": value},
            }
    return None


def _snapshot_summary(thread_id: str, snapshot: Any) -> dict[str, Any]:
    """把检查点快照压成可 JSON 序列化的审计摘要."""
    values = snapshot.values or {}
    configurable = (getattr(snapshot, "config", None) or {}).get("configurable", {})
    return {
        "thread_id": thread_id,
        "checkpoint_id": configurable.get("checkpoint_id"),
        "next": list(snapshot.next or ()),
        "pending_review": _pending_interrupt(snapshot) is not None,
        "current_node": values.get("current_node", ""),
        "agent_trace": values.get("agent_trace", []),
        "event_count": values.get("event_count", 0),
        "memory_hints_count": len(values.get("memory_hints", []) or []),
        "review_decision": values.get("review_decision", ""),
    }


def _node_action(agent: BaseAgent, idx: int, total: int) -> Any:
    """构造 LangGraph 节点动作.

    每个节点 = 一个自治智能体: 先推 NODE_START, 执行智能体, 广播 result 消息,
    再追加 NODE_COMPLETE (reviewer 追加 RISK_FOUND)。节点只返回本次新增的
    事件 / 消息 / 轨迹条目, 由状态归并器累加, 再交给 SSE 层回放。
    """

    async def action(state: AgentState) -> dict[str, Any]:
        before = state.model_dump()
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

        # 带归并器的字段只回传新增条目; 若回传完整状态, 历史条目会被重复累加。
        update = state_delta(before, state.model_dump())
        update["events"] = [event.model_dump() for event in events]
        # 单调游标: events 会被有界归并器裁剪, SSE 回放只能依赖累计计数
        update["event_count"] = int(before.get("event_count", 0)) + len(events)
        return update

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


async def _review_gate_node(state: AgentState) -> dict[str, Any]:
    """人工复核门: 高风险结论出报告前挂起, 由同 thread_id 的检查点续跑.

    interrupt() 会让本轮 astream 提前结束, 状态已由 checkpointer 落盘;
    续跑时 LangGraph 重放本节点, 并把 Command(resume=...) 的值交还给 decision。
    """
    if state.overall_level != RiskLevel.HIGH:
        return {"review_decision": "auto_approved"}

    decision = interrupt(
        {
            "contract_id": state.contract_id,
            "overall_level": state.overall_level.value,
            "overall_score": state.overall_score,
            "message": "高风险合同, 请人工复核后再发布审查结论",
        }
    )
    approved = decision.get("approved", True) if isinstance(decision, dict) else bool(decision)
    return {
        "review_decision": "approved" if approved else "rejected",
        "events": [
            SSEEvent(
                event=SSEEventType.THINKING,
                data={"message": "人工复核已通过, 继续生成审查报告" if approved else "人工复核未通过"},
            ).model_dump()
        ],
        # gate 不在 _node_action 包装里, 需自行推进事件游标, 否则该帧不会被回放
        "event_count": state.event_count + 1,
    }


@lru_cache
def build_contract_graph(mode: str = "multi") -> Any:
    """构建并编译 LangGraph 合同审查图 (按模式进程级缓存).

    编译时注入 checkpointer: 每个节点执行后落一份状态快照, thread_id = contract_id。
    """
    if mode not in ("multi", "linear"):
        mode = "multi"
    seq = _MULTI_SEQ if mode == "multi" else _LINEAR_SEQ
    total = len(seq)

    graph = StateGraph(AgentState)
    for idx, (name, _description) in enumerate(seq):
        graph.add_node(name, _node_action(_AGENTS[name], idx, total))

    gate_enabled = _review_gate_enabled()
    if gate_enabled:
        graph.add_node(_REVIEW_GATE, _review_gate_node)
    before_negotiator = _REVIEW_GATE if gate_enabled else "negotiator"

    graph.add_edge(START, seq[0][0])

    if mode == "linear":
        for i in range(total - 1):
            src, dst = seq[i][0], seq[i + 1][0]
            if dst == "negotiator" and gate_enabled:
                graph.add_edge(src, _REVIEW_GATE)
                graph.add_edge(_REVIEW_GATE, dst)
            else:
                graph.add_edge(src, dst)
        graph.add_edge(seq[-1][0], END)
    else:
        graph.add_edge("coordinator", "extractor")
        graph.add_edge("extractor", "retriever")
        graph.add_edge("retriever", "reviewer")
        graph.add_conditional_edges(
            "reviewer",
            _route_after_review,
            {"verifier": "verifier", "negotiator": before_negotiator},
        )
        graph.add_conditional_edges(
            "verifier",
            _route_after_verify,
            {"rework": "reviewer", "approve": before_negotiator},
        )
        if gate_enabled:
            graph.add_edge(_REVIEW_GATE, "negotiator")
        graph.add_edge("negotiator", END)

    checkpointer = get_checkpointer()
    compiled = graph.compile(checkpointer=checkpointer)
    logger.info(
        f"🕸️ LangGraph 工作流就绪 | 模式: {mode} | 检查点: "
        f"{'off' if checkpointer is None else type(checkpointer).__name__} | "
        f"复核门: {gate_enabled} | 节点: {[n for n, _ in seq]}"
    )
    return compiled


async def _reset_completed_thread(graph: Any, config: dict[str, Any]) -> None:
    """重新提交同一合同时清掉已完成的旧检查点, 避免新一轮串到旧状态.

    在途任务 (next 非空 / 有 pending interrupt) 一律不动。
    """
    saver = getattr(graph, "checkpointer", None)
    if saver is None:
        return
    snapshot = await graph.aget_state(config)
    if snapshot is None or not snapshot.values:
        return
    if snapshot.next or _pending_interrupt(snapshot) is not None:
        return
    thread_id = str(config["configurable"]["thread_id"])
    await saver.adelete_thread(thread_id)
    logger.info(f"🧹 重新分析: 已清理旧检查点 | thread={thread_id}")


async def run_contract_analysis(
    contract_id: str,
    raw_text: str,
    session: AsyncSession | None = None,
    contract_type: str = "",
    *,
    thread_id: str | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """
    执行 LangGraph 合同分析工作流, 异步生成 SSE 事件流.

    - 首跑前召回长期记忆写入 ``memory_hints``, 并清理同 thread 的旧终态快照;
    - 以 ``graph.astream`` 逐节点推进并回放节点事件;
    - 每个节点后由 checkpointer 落一份状态快照 (thread_id 默认为 contract_id);
    - NODE_START 由各节点自行推送, runner 只回放, 兼容线性/多智能体拓扑;
    - 全图结束后沉淀本次经验、持久化结果并推送 SUMMARY / COMPLETE。
    """
    mode = _current_mode()
    graph = build_contract_graph(mode)
    initial = AgentState(
        contract_id=contract_id,
        raw_text=raw_text,
        contract_type=contract_type,
        memory_hints=build_recall(contract_type),
    )
    config = graph_config(thread_id or contract_id)
    await _reset_completed_thread(graph, config)
    async for event in _stream_graph(
        graph,
        config,
        stream_input=initial,
        contract_id=contract_id,
        mode=mode,
        initial=initial,
        session=session,
    ):
        yield event


async def resume_contract_analysis(
    contract_id: str,
    *,
    thread_id: str | None = None,
    session: AsyncSession | None = None,
    approved: bool = True,
    checkpoint_id: str | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """从同一 thread_id 的检查点续跑 (人工复核通过 / 节点异常后重试).

    有 pending interrupt 时用 ``Command(resume=...)`` 交还复核结论;
    否则传 ``None``, 让 LangGraph 从最后一个未完成节点重新推进。
    """
    mode = _current_mode()
    graph = build_contract_graph(mode)
    if getattr(graph, "checkpointer", None) is None:
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": "检查点已关闭 (CHECKPOINT_BACKEND=off), 无法续跑"},
        )
        return

    config = graph_config(thread_id or contract_id, checkpoint_id=checkpoint_id)
    snapshot = await graph.aget_state(config)
    if snapshot is None or not snapshot.values:
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": "未找到可续跑的检查点, 请重新提交合同"},
        )
        return
    pending = _pending_interrupt(snapshot)
    if not snapshot.next and pending is None:
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": "该任务已完成, 无需续跑"},
        )
        return

    stream_input: Any = Command(resume={"approved": approved}) if pending else None
    async for event in _stream_graph(
        graph,
        config,
        stream_input=stream_input,
        contract_id=contract_id,
        mode=mode,
        initial=None,
        session=session,
    ):
        yield event


async def _stream_graph(
    graph: Any,
    config: dict[str, Any],
    *,
    stream_input: Any,
    contract_id: str,
    mode: str,
    initial: AgentState | None,
    session: AsyncSession | None,
) -> AsyncGenerator[SSEEvent, None]:
    """推进一次图执行: 首跑回放新增事件, 续跑跳过检查点里已回放的历史事件."""
    logger.info(
        f"🚀 Agent 工作流启动 (LangGraph/{mode}) | 合同ID: {contract_id}"
    )

    final_state: AgentState | None = initial
    emitted = 0
    if initial is None:
        snapshot = await graph.aget_state(config)
        values = snapshot.values if snapshot else {}
        if not values:
            yield SSEEvent(
                event=SSEEventType.ERROR,
                data={"message": "未找到可续跑的检查点, 请重新提交合同"},
            )
            return
        final_state = AgentState(**values)
        # 续跑游标用累计事件数, 不用 events 长度 (列表已被有界归并器裁剪)
        emitted = int(values.get("event_count", 0))

    try:
        async for raw in graph.astream(stream_input, config=config, stream_mode="values"):
            if initial is not None and emitted == 0 and raw == initial.model_dump():
                continue  # astream 首项为初始状态快照
            state = AgentState(**raw)
            final_state = state

            # 回放本节点新产生的事件 (NODE_START/THINKING/NODE_COMPLETE/RISK_FOUND)。
            # event_count 单调递增, events 只保留最近窗口, 因此按差值取尾部。
            new_count = state.event_count - emitted
            if new_count > 0:
                window = (
                    state.events[-new_count:]
                    if new_count <= len(state.events)
                    else state.events
                )
                for event in window:
                    yield event
                emitted = state.event_count
    except Exception as e:
        logger.exception(f"❌ LangGraph 工作流异常 | 合同ID: {contract_id}")
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": f"分析引擎异常: {e}"},
        )
        return

    assert final_state is not None
    # 人工复核门: interrupt 让 astream 提前结束, 状态已落检查点, 等待复核后续跑
    if getattr(graph, "checkpointer", None) is not None:
        snapshot = await graph.aget_state(config)
        pending = _pending_interrupt(snapshot)
        if pending is not None:
            yield SSEEvent(event=SSEEventType.AWAITING_REVIEW, data=pending)
            return
    if final_state.review_decision == "rejected":
        yield SSEEvent(
            event=SSEEventType.ERROR,
            data={"message": "人工复核未通过, 本次审查报告不发布"},
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
            # 本次召回到的长期记忆提示 (供前端展示 / 审计)
            "memory_hints": final_state.memory_hints,
            # 内容提示: 提交内容被判定为疑似非合同时非空, 前端据此在报告顶部标注
            "content_notice": content_notice,
        },
    )

    # 沉淀本次审查经验 (只写结构化摘要, 失败不影响报告产出)
    try:
        record_experience(final_state)
    except Exception:  # noqa: BLE001
        logger.exception("长期记忆写入失败 (不影响本次报告)")

    yield SSEEvent(
        event=SSEEventType.COMPLETE,
        data={"message": "✨ 合同风险排查完成！"},
    )

    logger.info(
        f"🏁 LangGraph 工作流完成 | 合同ID: {contract_id} | 模式: {mode} | "
        f"评分: {final_state.overall_score}/100 | 风险: {len(final_state.risk_assessments)} 项"
    )


async def get_checkpoint_state(
    thread_id: str, *, mode: str | None = None
) -> dict[str, Any] | None:
    """查询某 thread 的最新检查点摘要; 未启用检查点或无快照时返回 None."""
    graph = build_contract_graph(mode or _current_mode())
    if getattr(graph, "checkpointer", None) is None:
        return None
    snapshot = await graph.aget_state(graph_config(thread_id))
    if snapshot is None or not snapshot.values:
        return None
    return _snapshot_summary(thread_id, snapshot)


async def list_checkpoint_history(
    thread_id: str, *, limit: int = 20, mode: str | None = None
) -> list[dict[str, Any]]:
    """按时间倒序列出状态快照 (每个节点一份), 供审计与从历史分叉续跑."""
    graph = build_contract_graph(mode or _current_mode())
    if getattr(graph, "checkpointer", None) is None:
        return []
    history: list[dict[str, Any]] = []
    async for snapshot in graph.aget_state_history(graph_config(thread_id), limit=limit):
        history.append(_snapshot_summary(thread_id, snapshot))
    return history


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
