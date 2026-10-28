"""
LangGraph 断点续跑 / 重放测试.

用 memory 后端 (monkeypatch settings.checkpoint_backend=memory) 验证:
- 高风险合同: ``run_contract_analysis`` 在 review_gate 被 ``interrupt()`` 挂起
  (发 AWAITING_REVIEW, 不发 SUMMARY/COMPLETE), 状态落盘 (checkpoint);
- ``resume_contract_analysis``: 以同一 thread_id 从 checkpoint 续跑至 END
  (发 SUMMARY/COMPLETE);
- 中风险合同: 直接完成 (无中断, 发 SUMMARY/COMPLETE)。

无需真实 Postgres / MySQL (session=None 跳过落库)。生产后端 (postgres) 的
建表与连接逻辑由 lifespan 在部署环境启用, 此处只验证中断/续跑机制本身。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from app.agent.base import BaseAgent
from app.agent.graph import (
    build_contract_graph,
    resume_contract_analysis,
    run_contract_analysis,
)
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

_REVIEWER_JSON_HIGH = """{
  "risks": [
    {"category": "non_compete", "level": "high", "title": "竞业限制补偿金过低且违约金畸高",
     "original_clause": "乙方在职期间及离职后两年内，不得从事与甲方有竞争关系的业务，甲方每月支付竞业补偿金 1000 元；乙方违反约定的，应向甲方支付违约金 50 万元。",
     "explanation": "竞业限制期限内应按月给予经济补偿，未约定补偿的竞业限制条款存在被认定无效的风险。",
     "legal_basis": "《劳动合同法》第二十三条、第二十四条", "score": 30}
  ],
  "overall_score": 45, "overall_level": "high",
  "summary": "合同存在竞业限制补偿过低与违约金畸高的高风险条款。"
}"""

_REVIEWER_JSON_MEDIUM = """{
  "risks": [
    {"category": "non_compete", "level": "medium", "title": "竞业限制补偿金偏低",
     "original_clause": "乙方在职期间及离职后两年内，不得从事与甲方有竞争关系的业务，甲方每月支付竞业补偿金 1000 元；乙方违反约定的，应向甲方支付违约金 50 万元。",
     "explanation": "竞业限制期限内应按月给予经济补偿，未约定补偿的竞业限制条款存在被认定无效的风险。",
     "legal_basis": "《劳动合同法》第二十三条", "score": 65}
  ],
  "overall_score": 68, "overall_level": "medium",
  "summary": "合同整体风险中等，竞业限制补偿偏低。"
}"""

_NEGOTIATOR_JSON = '{"contract_facts": {"employer": "星辰科技有限公司"}}'


def _collect(agen: AsyncGenerator[SSEEvent, None]) -> list[SSEEvent]:
    async def _drain() -> list[SSEEvent]:
        out: list[SSEEvent] = []
        async for e in agen:
            out.append(e)
        return out

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_drain())
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def memory_checkpointer(monkeypatch) -> None:
    """强制 memory 后端并清图编译缓存, 避免默认 postgres 在测试环境连库失败."""
    settings = get_settings()
    monkeypatch.setattr(settings, "checkpoint_backend", "memory")
    build_contract_graph.cache_clear()
    yield
    build_contract_graph.cache_clear()


@pytest.fixture
def fake_llm_high(monkeypatch) -> None:
    async def fake_invoke(
        self: BaseAgent, user_message: str, *, temperature=None, max_tokens=4096
    ) -> str:
        if self.name == "extractor":
            return _EXTRACTOR_JSON
        if self.name == "reviewer":
            return _REVIEWER_JSON_HIGH
        if self.name == "negotiator":
            return _NEGOTIATOR_JSON
        raise AssertionError(f"意外调用 LLM 的节点: {self.name}")

    monkeypatch.setattr(BaseAgent, "invoke_llm", fake_invoke)


@pytest.fixture
def fake_llm_medium(monkeypatch) -> None:
    async def fake_invoke(
        self: BaseAgent, user_message: str, *, temperature=None, max_tokens=4096
    ) -> str:
        if self.name == "extractor":
            return _EXTRACTOR_JSON
        if self.name == "reviewer":
            return _REVIEWER_JSON_MEDIUM
        if self.name == "negotiator":
            return _NEGOTIATOR_JSON
        raise AssertionError(f"意外调用 LLM 的节点: {self.name}")

    monkeypatch.setattr(BaseAgent, "invoke_llm", fake_invoke)


@pytest.fixture
def fake_mcp(monkeypatch) -> None:
    async def fake_call(self: MCPClient, tool_name: str, **arguments: object) -> object:
        if tool_name == "law_search":
            return {
                "results": [
                    {"law_name": "劳动合同法", "article": "第二十三条",
                     "content": "条文内容。", "similarity": 0.92}
                ]
            }
        if tool_name == "negotiation":
            return {"negotiation_tip": "建议沟通。"}
        raise AssertionError(f"意外调用 MCP 工具: {tool_name}")

    monkeypatch.setattr(MCPClient, "call", fake_call)


def _events_seq(events: list[SSEEvent]) -> list[str]:
    return [e.event.value for e in events]


class TestResumeWorkflow:
    def test_high_risk_suspends_then_resume_publishes(
        self, fake_llm_high, fake_mcp, memory_checkpointer
    ) -> None:
        # 首跑: 高风险应被 interrupt 挂起 (发 AWAITING_REVIEW, 不发 SUMMARY/COMPLETE)
        first = _collect(run_contract_analysis("resume-c1", _CONTRACT_TEXT))
        seq1 = _events_seq(first)
        assert SSEEventType.AWAITING_REVIEW.value in seq1
        assert SSEEventType.SUMMARY.value not in seq1
        assert SSEEventType.COMPLETE.value not in seq1

        # 状态已落盘 (checkpoint): 同 thread_id 能取得暂停态 (next 非空)
        graph = build_contract_graph()
        cfg = {"configurable": {"thread_id": "resume-c1"}}
        snap = asyncio.new_event_loop().run_until_complete(graph.aget_state(cfg))
        assert snap.next, "高风险合同应处于 interrupt 暂停态"

        # 续跑: 从 checkpoint 恢复到 END 并发布
        second = _collect(resume_contract_analysis("resume-c1", None))
        seq2 = _events_seq(second)
        assert SSEEventType.AWAITING_REVIEW.value not in seq2
        assert seq2[-2] == SSEEventType.SUMMARY.value
        assert seq2[-1] == SSEEventType.COMPLETE.value

    def test_medium_risk_completes_directly(
        self, fake_llm_medium, fake_mcp, memory_checkpointer
    ) -> None:
        events = _collect(run_contract_analysis("resume-c2", _CONTRACT_TEXT))
        seq = _events_seq(events)
        assert SSEEventType.AWAITING_REVIEW.value not in seq
        assert seq[-2] == SSEEventType.SUMMARY.value
        assert seq[-1] == SSEEventType.COMPLETE.value
