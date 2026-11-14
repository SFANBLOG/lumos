"""
Agent 记忆管理测试.

覆盖:
- 工作记忆: 有界追加归并器, 事件窗口裁剪后 SSE 回放不丢帧;
- 长期记忆: CRUD / 过期 / 命名空间隔离与容量淘汰 / 经验召回 / 反馈回流;
- 短期记忆: 检查点 TTL 与最大 thread 数清理;
- 缺陷回归: 重复提交串状态、重置后端时连接泄漏、复核门续跑丢事件帧。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.base import empty_checkpoint

from app.agent import checkpoint as checkpoint_module
from app.agent import memory as mem
from app.agent.base import BaseAgent
from app.agent.checkpoint import graph_config
from app.agent.graph import (
    build_contract_graph,
    get_checkpoint_state,
    list_checkpoint_history,
    run_contract_analysis,
)
from app.agent.reducers import append_events, bounded_append, state_delta
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


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """每个用例重置 Store / checkpointer / 图缓存, 避免跨用例串记忆."""
    monkeypatch.setenv("AGENT_MODE", "linear")
    settings = get_settings()
    for key, value in (
        ("memory_enabled", True),
        ("memory_max_events", 200),
        ("memory_max_messages", 200),
        ("memory_max_trace", 100),
        ("memory_max_errors", 50),
        ("memory_ttl_hours", 24.0),
        ("memory_max_items_per_namespace", 50),
        ("memory_checkpoint_ttl_hours", 72.0),
        ("memory_max_threads", 500),
        ("checkpoint_backend", "memory"),
        ("checkpoint_review_gate", False),
    ):
        monkeypatch.setattr(settings, key, value)
    mem.reset_memory_store()
    checkpoint_module.reset_checkpointer()
    build_contract_graph.cache_clear()
    yield
    mem.reset_memory_store()
    checkpoint_module.reset_checkpointer()
    build_contract_graph.cache_clear()


@pytest.fixture
def fake_llm(monkeypatch) -> None:
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
            return {"negotiation_tip": "建议与 HR 沟通竞业限制补偿标准。"}
        raise AssertionError(f"意外调用 MCP 的工具: {tool_name}")

    monkeypatch.setattr(MCPClient, "call", fake_call)


def _collect(agen: AsyncGenerator[SSEEvent, None]) -> list[SSEEvent]:
    async def _drain() -> list[SSEEvent]:
        return [event async for event in agen]

    return asyncio.run(_drain())


def _fake_state() -> SimpleNamespace:
    return SimpleNamespace(
        contract_type="labor_contract",
        contract_id="c-memory",
        risk_assessments=[SimpleNamespace(category="non_compete")],
        overall_score=45,
        overall_level="high",
        review_rounds=0,
        event_count=9,
        review_decision="",
    )


def _write_checkpoint(thread_id: str, age_hours: float = 0.0) -> None:
    """直接往 saver 写一份快照, 用于验证清理策略."""
    saver = checkpoint_module.get_checkpointer()
    assert saver is not None
    checkpoint = empty_checkpoint()
    checkpoint["ts"] = (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat()
    config = graph_config(thread_id)
    config["configurable"]["checkpoint_ns"] = ""
    asyncio.run(
        saver.aput(
            config,
            checkpoint,
            {"source": "loop", "step": 1, "writes": None, "parents": {}},
            {},
        )
    )


# ─── 工作记忆 ────────────────────────────────────────────────


class TestWorkingMemory:
    def test_bounded_append_keeps_last_items(self) -> None:
        assert bounded_append([1, 2, 3], [4, 5], 3) == [3, 4, 5]
        assert bounded_append(None, [1], 0) == [1]
        assert state_delta({"events": [1], "x": 1}, {"events": [1, 2], "x": 2})["events"] == [2]

    def test_event_reducer_respects_configured_limit(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "memory_max_events", 3)
        assert append_events([1, 2, 3], [4]) == [2, 3, 4]

    def test_event_window_trim_does_not_lose_sse_frames(
        self, monkeypatch, fake_llm: None, fake_mcp: None
    ) -> None:
        """事件列表被裁到 3 条, SSE 仍应完整回放全部节点帧."""
        monkeypatch.setattr(get_settings(), "memory_max_events", 3)
        cid = "mem-window"
        events = _collect(run_contract_analysis(contract_id=cid, raw_text=_CONTRACT_TEXT))
        assert [e.event for e in events] == [
            SSEEventType.NODE_START,
            SSEEventType.NODE_COMPLETE,
            SSEEventType.NODE_START,
            SSEEventType.NODE_COMPLETE,
            SSEEventType.NODE_START,
            SSEEventType.NODE_COMPLETE,
            SSEEventType.RISK_FOUND,
            SSEEventType.NODE_START,
            SSEEventType.NODE_COMPLETE,
            SSEEventType.SUMMARY,
            SSEEventType.COMPLETE,
        ]
        state = asyncio.run(get_checkpoint_state(cid))
        assert state is not None
        assert state["event_count"] == 9  # 单调游标, 不受裁剪影响

    def test_rerun_clears_completed_thread(self, fake_llm: None, fake_mcp: None) -> None:
        """同一合同重新提交: 旧终态快照清掉, 轨迹不能串成两轮."""
        cid = "mem-rerun"
        assert _collect(run_contract_analysis(contract_id=cid, raw_text=_CONTRACT_TEXT))[-1].event == SSEEventType.COMPLETE
        assert len(asyncio.run(list_checkpoint_history(cid))) >= 4

        assert _collect(run_contract_analysis(contract_id=cid, raw_text=_CONTRACT_TEXT))[-1].event == SSEEventType.COMPLETE
        state = asyncio.run(get_checkpoint_state(cid))
        assert state is not None
        assert state["agent_trace"] == [
            "extractor",
            "retriever",
            "reviewer",
            "negotiator",
        ]


# ─── 长期记忆 ────────────────────────────────────────────────


class TestLongTermMemory:
    def test_crud_expiry_and_namespace_isolation(self) -> None:
        ns = ("agent", "unit", "a")
        other = ("agent", "unit", "b")
        mem.put_memory(ns, "k", {"v": 1}, ttl_hours=1)
        mem.put_memory(other, "k", {"v": 2}, ttl_hours=1)
        assert mem.get_memory(ns, "k") == {"v": 1}
        assert mem.get_memory(other, "k") == {"v": 2}
        assert len(mem.search_memories(("agent", "unit"), limit=10)) == 2

        store = mem.get_memory_store()
        item = store.get(ns, "k")
        assert item is not None
        expired = {**item.value, "_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
        store.put(ns, "k", expired)
        assert mem.get_memory(ns, "k") is None
        assert mem.get_memory(other, "k") == {"v": 2}

        mem.delete_memory(other, "k")
        assert mem.get_memory(other, "k") is None

    def test_namespace_capacity_eviction(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "memory_max_items_per_namespace", 3)
        ns = ("agent", "evict", "ns")
        for i in range(6):
            mem.put_memory(ns, f"k{i}", {"i": i})
        assert len(mem.search_memories(ns, limit=20)) == 3

    def test_experience_roundtrip_and_recall(self) -> None:
        mem.record_experience(_fake_state())
        mem.record_experience(_fake_state())
        exp = mem.get_memory(("agent", "experience", "labor_contract"), "summary")
        assert exp is not None
        assert exp["count"] == 2
        assert exp["category_counts"]["non_compete"] == 2
        assert mem.get_memory(("agent", "thread", "c-memory"), "last_run") is not None

        hints = mem.build_recall("labor_contract")
        assert any("高频风险类别" in hint for hint in hints)
        assert any("平均评分" in hint for hint in hints)
        # 经验只存结构化摘要, 绝不写合同原文
        assert all(_CONTRACT_TEXT[:20] not in str(hint) for hint in hints)

    def test_feedback_feeds_recall(self) -> None:
        for _ in range(3):
            mem.record_feedback("non_compete", "false_positive")
        mem.record_feedback("non_compete", "ignored")  # 忽略不计入
        hints = mem.build_recall("labor_contract")
        assert any("误报率偏高" in hint for hint in hints)

    def test_disabled_memory_is_noop(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "memory_enabled", False)
        mem.put_memory(("agent", "off"), "k", {"v": 1})
        mem.record_experience(_fake_state())
        assert mem.get_memory(("agent", "off"), "k") is None
        assert mem.build_recall("labor_contract") == []

    def test_stats_report_backends(self) -> None:
        stats = mem.get_memory_stats()
        assert stats["enabled"] is True
        assert stats["store_backend"] == "InMemoryStore"
        assert stats["checkpoint_backend"] == "InMemorySaver"


# ─── 短期记忆清理 ────────────────────────────────────────────


class TestCheckpointPruning:
    def test_ttl_removes_expired_threads(self) -> None:
        _write_checkpoint("mem-old", age_hours=100)
        _write_checkpoint("mem-fresh", age_hours=0)
        result = asyncio.run(mem.prune_expired_checkpoints(force=True))
        assert result["deleted"] == 1
        assert result["kept"] == 1

    def test_capacity_evicts_oldest_threads(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "memory_max_threads", 1)
        _write_checkpoint("mem-t1", age_hours=3)
        _write_checkpoint("mem-t2", age_hours=2)
        _write_checkpoint("mem-t3", age_hours=1)
        result = asyncio.run(mem.prune_expired_checkpoints(force=True))
        assert result["deleted"] == 2
        assert result["kept"] == 1

    def test_throttled_call_is_skipped(self) -> None:
        asyncio.run(mem.prune_expired_checkpoints(force=True))
        result = asyncio.run(mem.prune_expired_checkpoints())
        assert result.get("skipped") == 1

    def test_reset_closes_sqlite_connection(self, monkeypatch, tmp_path: Path) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "checkpoint_backend", "sqlite")
        monkeypatch.setattr(settings, "checkpoint_sqlite_path", str(tmp_path / "ck.sqlite"))
        checkpoint_module.reset_checkpointer()
        build_contract_graph.cache_clear()
        assert checkpoint_module.get_checkpointer() is not None
        # 不应抛异常, 也不应遗留未关闭的异步连接
        checkpoint_module.reset_checkpointer()
        assert checkpoint_module.get_checkpointer.cache_info().currsize == 0


class TestLongTermMemoryPruning:
    def test_expired_items_are_purged_without_being_read(self) -> None:
        ns = ("agent", "unit", "expire")
        mem.put_memory(ns, "k", {"v": 1}, ttl_hours=1)
        store = mem.get_memory_store()
        item = store.get(ns, "k")
        assert item is not None
        store.put(
            ns,
            "k",
            {
                **item.value,
                "_expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            },
        )
        assert mem.prune_expired_memories() == 1
        assert mem.get_memory(ns, "k") is None

    def test_thread_namespaces_respect_capacity(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "memory_max_threads", 2)
        for i in range(5):
            mem.put_memory(("agent", "thread", f"c{i}"), "last_run", {"i": i})
        assert mem.prune_expired_memories() == 3
        assert len(mem.search_memories(("agent", "thread"), limit=20)) == 2

    def test_prune_entry_reports_memory_cleanup(self) -> None:
        mem.put_memory(("agent", "unit", "ok"), "k", {"v": 1}, ttl_hours=24)
        result = asyncio.run(mem.prune_expired_checkpoints(force=True))
        assert "memories_deleted" in result
        assert mem.get_memory(("agent", "unit", "ok"), "k") == {"v": 1}
