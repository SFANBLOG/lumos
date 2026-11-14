"""
LangGraph 状态归并器 / 检查点测试.

覆盖:
- 追加归并器只累加节点新增条目 (事件 / 消息 / 轨迹 / 错误不重复);
- checkpointer 逐节点落快照, 可查询状态与历史;
- 人工复核门 interrupt 挂起 → 同 thread_id 用 Command(resume=...) 续跑;
- backend=off 保持旧行为, backend=sqlite 落盘可跨连接读取。

不依赖真实大模型 / Milvus / MinIO, 以 monkeypatch 注入假 LLM 与 MCP 结果。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from langgraph.graph import StateGraph

from app.agent import checkpoint as checkpoint_module
from app.agent.base import BaseAgent
from app.agent.checkpoint import graph_config
from app.agent.graph import (
    build_contract_graph,
    get_checkpoint_state,
    list_checkpoint_history,
    resume_contract_analysis,
    run_contract_analysis,
)
from app.agent.reducers import append_list, state_delta
from app.agent.state import AgentState
from app.core.config import get_settings
from app.mcp.client import MCPClient
from app.schemas.analysis import SSEEvent, SSEEventType

_CONTRACT_TEXT = """甲方：星辰科技有限公司

一、竞业限制：乙方在职期间及离职后两年内，不得从事与甲方有竞争关系的业务，甲方每月支付竞业补偿金 1000 元；乙方违反约定的，应向甲方支付违约金 50 万元。

二、试用期：试用期为 6 个月，试用期工资按转正工资的 60% 发放。

甲方（盖章）：星辰科技有限公司
"""

_EXTRACTOR_JSON = """[
  {"clause_index": 1, "title": "竞业限制", "content": "乙方在职期间及离职后两年内，不得从事与甲方有竞争关系的业务，甲方每月支付竞业补偿金 1000 元；乙方违反约定的，应向甲方支付违约金 50 万元。", "category": "non_compete"},
  {"clause_index": 2, "title": "试用期", "content": "试用期为 6 个月，试用期工资按转正工资的 60% 发放。", "category": "probation_salary"}
]"""

_REVIEWER_JSON = """{
  "risks": [
    {
      "category": "non_compete",
      "level": "high",
      "title": "竞业限制补偿金过低且违约金畸高",
      "original_clause": "乙方在职期间及离职后两年内，不得从事与甲方有竞争关系的业务，甲方每月支付竞业补偿金 1000 元；乙方违反约定的，应向甲方支付违约金 50 万元。",
      "explanation": "竞业限制期限内应按月给予经济补偿，未约定补偿的竞业限制条款存在被认定无效的风险。",
      "legal_basis": "《劳动合同法》第二十三条、第二十四条",
      "score": 30
    }
  ],
  "overall_score": 45,
  "overall_level": "high",
  "summary": "合同存在竞业限制补偿过低与违约金畸高的高风险条款。"
}"""


@pytest.fixture
def fake_llm(monkeypatch) -> None:
    """按智能体名称返回固定假 LLM 输出."""

    async def fake_invoke(
        self: BaseAgent,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        if self.name == "extractor":
            return _EXTRACTOR_JSON
        if self.name == "reviewer":
            return _REVIEWER_JSON
        raise AssertionError(f"意外调用 LLM 的节点: {self.name}")

    monkeypatch.setattr(BaseAgent, "invoke_llm", fake_invoke)


@pytest.fixture
def fake_mcp(monkeypatch) -> None:
    """按工具名返回固定假 MCP 结果."""

    async def fake_call(self: MCPClient, tool_name: str, **arguments: object) -> object:
        if tool_name == "law_search":
            return {
                "results": [
                    {
                        "law_name": "劳动合同法",
                        "article": "第二十三条",
                        "content": "《劳动合同法》第二十三条相关条文内容。",
                        "similarity": 0.92,
                    }
                ]
            }
        if tool_name == "negotiation":
            return {"negotiation_tip": "建议与 HR 沟通竞业限制补偿标准与违约金上限。"}
        raise AssertionError(f"意外调用 MCP 的工具: {tool_name}")

    monkeypatch.setattr(MCPClient, "call", fake_call)


@pytest.fixture(autouse=True)
def _isolated_checkpoint(monkeypatch):
    """每个用例重置后端单例与图缓存, 避免跨用例串状态."""
    monkeypatch.setenv("AGENT_MODE", "linear")
    settings = get_settings()
    monkeypatch.setattr(settings, "checkpoint_backend", "memory")
    monkeypatch.setattr(settings, "checkpoint_review_gate", False)
    checkpoint_module.reset_checkpointer()
    build_contract_graph.cache_clear()
    yield
    checkpoint_module.reset_checkpointer()
    build_contract_graph.cache_clear()


def _collect(agen: AsyncGenerator[SSEEvent, None]) -> list[SSEEvent]:
    async def _drain() -> list[SSEEvent]:
        return [event async for event in agen]

    return asyncio.run(_drain())


def _enable_gate(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "checkpoint_review_gate", True)
    checkpoint_module.reset_checkpointer()
    build_contract_graph.cache_clear()


class TestReducer:
    def test_append_fields_are_aggregate_channels(self) -> None:
        channels = StateGraph(AgentState).channels
        for field in ("errors", "agent_trace", "agent_messages", "events"):
            assert type(channels[field]).__name__ == "BinaryOperatorAggregate"
        # 结论型列表仍是覆盖语义, 返工重审不会被累加成两份
        assert type(channels["risk_assessments"]).__name__ == "LastValue"

    def test_append_list_and_state_delta(self) -> None:
        assert append_list([1, 2], [3]) == [1, 2, 3]
        assert append_list(None, None) == []
        delta = state_delta(
            {"events": ["a"], "errors": [], "x": 1},
            {"events": ["a", "b"], "errors": ["e"], "x": 2},
        )
        assert delta == {
            "x": 2,
            "events": ["b"],
            "errors": ["e"],
            "agent_trace": [],
            "agent_messages": [],
        }

    def test_graph_run_does_not_duplicate_appended_items(
        self, fake_llm: None, fake_mcp: None
    ) -> None:
        graph = build_contract_graph("linear")
        raw = asyncio.run(
            graph.ainvoke(
                AgentState(contract_id="cp-reducer", raw_text=_CONTRACT_TEXT),
                config=graph_config("cp-reducer"),
            )
        )
        state = AgentState(**raw)
        assert state.agent_trace == [
            "extractor",
            "retriever",
            "reviewer",
            "negotiator",
        ]
        assert len(state.agent_messages) == 4
        # 4 个节点各 START/COMPLETE + 1 条 RISK_FOUND
        assert len(state.events) == 9
        assert len(state.risk_assessments) == 1


class TestCheckpoint:
    def test_graph_is_compiled_with_checkpointer(self) -> None:
        graph = build_contract_graph("linear")
        assert graph.checkpointer is not None

    def test_state_and_history_are_persisted(
        self, fake_llm: None, fake_mcp: None
    ) -> None:
        cid = "cp-history"
        events = _collect(run_contract_analysis(contract_id=cid, raw_text=_CONTRACT_TEXT))
        assert events[-1].event == SSEEventType.COMPLETE

        state = asyncio.run(get_checkpoint_state(cid))
        assert state is not None
        assert state["thread_id"] == cid
        assert state["checkpoint_id"]
        assert state["agent_trace"] == [
            "extractor",
            "retriever",
            "reviewer",
            "negotiator",
        ]

        history = asyncio.run(list_checkpoint_history(cid))
        assert len(history) >= 4
        assert all(item["thread_id"] == cid for item in history)

    def test_review_gate_suspends_then_resumes(
        self, monkeypatch, fake_llm: None, fake_mcp: None
    ) -> None:
        _enable_gate(monkeypatch)
        cid = "cp-gate"
        first = _collect(run_contract_analysis(contract_id=cid, raw_text=_CONTRACT_TEXT))
        seq = [event.event for event in first]
        assert seq[-1] == SSEEventType.AWAITING_REVIEW
        assert SSEEventType.SUMMARY not in seq
        assert SSEEventType.COMPLETE not in seq

        paused = asyncio.run(get_checkpoint_state(cid))
        assert paused is not None
        assert paused["pending_review"] is True
        assert "review_gate" in paused["next"]

        second = _collect(resume_contract_analysis(cid))
        seq2 = [event.event for event in second]
        assert SSEEventType.SUMMARY in seq2
        assert seq2[-1] == SSEEventType.COMPLETE

        final = asyncio.run(get_checkpoint_state(cid))
        assert final is not None
        assert final["review_decision"] == "approved"
        assert final["pending_review"] is False
        # 续跑不重放已完成节点, 归并器也不重复累加轨迹
        assert final["agent_trace"] == [
            "extractor",
            "retriever",
            "reviewer",
            "negotiator",
        ]

    def test_backend_off_keeps_legacy_behaviour(
        self, monkeypatch, fake_llm: None, fake_mcp: None
    ) -> None:
        monkeypatch.setattr(get_settings(), "checkpoint_backend", "off")
        checkpoint_module.reset_checkpointer()
        build_contract_graph.cache_clear()

        assert build_contract_graph("linear").checkpointer is None
        assert asyncio.run(get_checkpoint_state("cp-off")) is None
        events = _collect(
            run_contract_analysis(contract_id="cp-off", raw_text=_CONTRACT_TEXT)
        )
        assert events[-1].event == SSEEventType.COMPLETE

    def test_sqlite_backend_writes_history(
        self, monkeypatch, tmp_path: Path, fake_llm: None, fake_mcp: None
    ) -> None:
        settings = get_settings()
        db_path = tmp_path / "checkpoints.sqlite"
        monkeypatch.setattr(settings, "checkpoint_backend", "sqlite")
        monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(db_path))
        checkpoint_module.reset_checkpointer()
        build_contract_graph.cache_clear()

        cid = "cp-sqlite"
        events = _collect(run_contract_analysis(contract_id=cid, raw_text=_CONTRACT_TEXT))
        assert events[-1].event == SSEEventType.COMPLETE
        assert db_path.is_file()

        # 新 saver 连接同一文件, 仍能读到历史快照 (跨连接 / 跨进程重启)
        checkpoint_module.reset_checkpointer()
        build_contract_graph.cache_clear()
        history = asyncio.run(list_checkpoint_history(cid))
        assert len(history) >= 4


class TestResumeTask:
    def test_resume_analysis_restarts_finished_session(self, monkeypatch) -> None:
        from app.services import analysis_task as at

        sess = at._TaskSession()
        sess.done = True  # 复核门挂起后该会话已结束
        at._sessions["cp-resume"] = sess

        async def fake_runner(*args: object, **kwargs: object) -> None:
            return None

        monkeypatch.setattr(at, "_runner", fake_runner)

        async def scenario() -> bool:
            ok = at.resume_analysis("cp-resume")
            await asyncio.sleep(0.01)
            return ok

        try:
            assert asyncio.run(scenario()) is True
            assert sess.done is False  # SSE 重连可继续跟随推送
            assert sess.task is not None
        finally:
            at._sessions.pop("cp-resume", None)

    def test_gate_resume_through_background_task(
        self, monkeypatch, fake_llm: None, fake_mcp: None
    ) -> None:
        """复核门挂起 → 后台任务续跑 → SSE 缓冲里补齐 SUMMARY/COMPLETE."""
        from app.services import analysis_task as at

        _enable_gate(monkeypatch)
        cid = "cp-e2e-resume"

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, _model, _pk):
                return None

            async def commit(self):
                return None

        def fake_resume(*, contract_id: str, session: object = None):
            return resume_contract_analysis(contract_id=contract_id, session=None)

        monkeypatch.setattr(at, "async_session_factory", _FakeSession)
        monkeypatch.setattr(at, "resume_contract_analysis", fake_resume)

        first = _collect(run_contract_analysis(contract_id=cid, raw_text=_CONTRACT_TEXT))
        assert first[-1].event == SSEEventType.AWAITING_REVIEW

        sess = at._TaskSession()
        sess.events.extend(first)
        sess.done = True
        at._sessions[cid] = sess

        async def scenario() -> list[SSEEventType]:
            assert at.resume_analysis(cid)
            for _ in range(100):
                if sess.done:
                    break
                await asyncio.sleep(0.02)
            return [event.event for event in sess.events]

        try:
            seq = asyncio.run(scenario())
            assert SSEEventType.SUMMARY in seq
            assert seq[-1] == SSEEventType.COMPLETE
        finally:
            at._sessions.pop(cid, None)
