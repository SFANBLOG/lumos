"""
LangGraph 工作流测试.

以 monkeypatch 注入假 LLM 输出与 MCP 工具结果, 不依赖真实大模型/
Milvus/MinIO 等外部服务, 验证:
- 图节点顺序与状态推进 (extract → retrieve → review → negotiate);
- SSE 事件流协议时序 (NODE_START/NODE_COMPLETE/RISK_FOUND/SUMMARY/COMPLETE);
- 子智能体失败时的降级与 THINKING 事件。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from app.agent.base import BaseAgent
from app.agent.graph import build_contract_graph, run_contract_analysis
from app.agent.state import AgentState
from app.agent.sub_agents.reviewer_agent import ReviewerAgent
from app.mcp.client import MCPClient
from app.schemas.analysis import SSEEvent, SSEEventType

_CONTRACT_TEXT = """甲方：星辰科技有限公司

一、竞业限制：乙方在职期间及离职后两年内，不得从事与甲方有竞争关系的业务，甲方每月支付竞业补偿金 1000 元；乙方违反约定的，应向甲方支付违约金 50 万元。

二、试用期：试用期为 6 个月，试用期工资按转正工资的 60% 发放。

三、工作内容：乙方担任软件工程师，具体工作内容由甲方根据经营需要安排。

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


def _law_refs(article: str) -> dict:
    return {
        "law_name": "劳动合同法",
        "article": article,
        "content": f"《劳动合同法》{article}相关条文内容。",
        "similarity": 0.92,
    }


@pytest.fixture
def fake_llm(monkeypatch) -> None:
    """按智能体名称返回固定的假 LLM 输出."""

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
    """按工具名返回固定的假 MCP 结果."""

    async def fake_call(self: MCPClient, tool_name: str, **arguments: object) -> object:
        if tool_name == "law_search":
            return {
                "results": [
                    _law_refs("第二十三条"),
                    _law_refs("第二十四条"),
                ]
            }
        if tool_name == "negotiation":
            return {"negotiation_tip": "建议与 HR 沟通竞业限制补偿标准与违约金上限。"}
        raise AssertionError(f"意外调用 MCP 工具: {tool_name}")

    monkeypatch.setattr(MCPClient, "call", fake_call)


@pytest.fixture
def sample_state() -> AgentState:
    return AgentState(contract_id="test-contract", raw_text=_CONTRACT_TEXT)


def _collect(agen: AsyncGenerator[SSEEvent, None]) -> list[SSEEvent]:
    """同步收集异步事件生成器 (每次新建事件循环, 避免跨用例污染)."""
    import asyncio

    async def _drain() -> list[SSEEvent]:
        return [event async for event in agen]

    return asyncio.run(_drain())


class TestWorkflowGraph:
    def test_graph_contains_four_stage_nodes(self) -> None:
        graph = build_contract_graph()
        node_names = set(graph.get_graph().nodes.keys())
        assert {"extractor", "retriever", "reviewer", "negotiator"} <= node_names

    def test_state_flows_through_pipeline(self, fake_llm, fake_mcp) -> None:
        import asyncio

        graph = build_contract_graph()
        raw = asyncio.run(
            graph.ainvoke(AgentState(contract_id="g-1", raw_text=_CONTRACT_TEXT))
        )
        st = raw if isinstance(raw, AgentState) else AgentState(**raw)
        assert st.agent_trace == ["extractor", "retriever", "reviewer", "negotiator"]
        assert len(st.extracted_clauses) == 2
        assert len(st.legal_references) >= 1
        assert len(st.risk_assessments) == 1
        assert st.risk_assessments[0].negotiation_tip  # negotiator 已补全话术
        assert st.overall_score == 45
        assert st.overall_level.value == "high"

    def test_events_timeline_protocol(self, fake_llm, fake_mcp, sample_state) -> None:
        events = _collect(
            run_contract_analysis(contract_id=sample_state.contract_id, raw_text=sample_state.raw_text)
        )
        seq = [e.event for e in events]
        assert seq == [
            SSEEventType.NODE_START,   # extractor
            SSEEventType.NODE_COMPLETE,
            SSEEventType.NODE_START,   # retriever
            SSEEventType.NODE_COMPLETE,
            SSEEventType.NODE_START,   # reviewer
            SSEEventType.NODE_COMPLETE,
            SSEEventType.RISK_FOUND,   # 风险逐条上屏 (reviewer 之后)
            SSEEventType.NODE_START,   # negotiator
            SSEEventType.NODE_COMPLETE,
            SSEEventType.SUMMARY,
            SSEEventType.COMPLETE,
        ]
        # RISK_FOUND 载荷与风险条目一致
        risk_event = next(e for e in events if e.event == SSEEventType.RISK_FOUND)
        assert risk_event.data["category"] == "non_compete"
        assert risk_event.data["level"] == "high"
        # SUMMARY 汇总口径
        summary = next(e for e in events if e.event == SSEEventType.SUMMARY)
        assert summary.data["total_clauses"] == 2
        assert summary.data["total_risks"] == 1
        assert summary.data["overall_score"] == 45

    def test_node_error_emits_thinking_and_finishes(
        self, monkeypatch, fake_llm, fake_mcp
    ) -> None:
        """reviewer 运行期异常 → BaseAgent 捕获 → THINKING 提示, 流程继续."""

        async def broken_reviewer_run(self: ReviewerAgent, state: AgentState) -> AgentState:
            raise RuntimeError("审查引擎内部错误")

        monkeypatch.setattr(ReviewerAgent, "run", broken_reviewer_run)
        events = _collect(
            run_contract_analysis(contract_id="t-err", raw_text=_CONTRACT_TEXT)
        )
        seq = [e.event for e in events]
        assert SSEEventType.THINKING in seq
        assert SSEEventType.SUMMARY in seq
        assert SSEEventType.COMPLETE in seq
        summary = next(e for e in events if e.event == SSEEventType.SUMMARY)
        # extractor/retriever 正常推进; reviewer 失败不阻断后续节点
        assert summary.data["total_clauses"] == 2
        assert summary.data["total_risks"] == 0


class TestAnalysisTaskBuffer:
    """后台任务化: 事件缓冲回放 + 断线后任务不受影响."""

    def test_replays_buffered_events_after_completion(self, monkeypatch) -> None:
        import asyncio

        from app.services import analysis_task as at

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, _model, _pk):
                return None

            async def commit(self):
                pass

        async def fake_run(contract_id, raw_text, session=None):  # noqa: ARG001
            yield SSEEvent(event=SSEEventType.NODE_COMPLETE, data={"node_name": "extractor"})
            await asyncio.sleep(0.05)
            yield SSEEvent(event=SSEEventType.COMPLETE, data={"message": "ok"})

        monkeypatch.setattr(at, "async_session_factory", _FakeSession)
        monkeypatch.setattr(at, "run_contract_analysis", fake_run)

        async def scenario():
            at.start_analysis("buf-1", "text")
            first = [e async for e in at.stream_events("buf-1")]
            # 任务已结束: 重连仍可完整回放 (SSE 断线场景)
            second = [e async for e in at.stream_events("buf-1")]
            return first, second

        try:
            first, second = asyncio.run(scenario())
            assert [e.event for e in first] == [
                SSEEventType.NODE_COMPLETE,
                SSEEventType.COMPLETE,
            ]
            assert [e.event for e in second] == [e.event for e in first]
        finally:
            at._sessions.pop("buf-1", None)
