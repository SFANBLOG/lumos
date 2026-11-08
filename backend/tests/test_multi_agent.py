"""
多智能体协作工作流测试.

验证默认 ``AGENT_MODE=multi`` 下的真实多智能体行为:
- Coordinator 动态编排并通过消息总线下发任务;
- 各智能体广播 result, Verifier 独立复核并交接;
- Verifier 可否决结论, 由条件边触发 Reviewer 返工 (受轮次上限约束);
- SSE 时间线、fail-loud 与报告兼容多智能体拓扑。

不依赖真实大模型 / Milvus / MinIO, 以 monkeypatch 注入假 LLM 与 MCP 结果。
"""

from __future__ import annotations

import asyncio
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

#: 法条引用不可溯源, 用于触发 Verifier 否决与返工
_REVIEWER_JSON_BAD = _REVIEWER_JSON.replace("第二十三条、第二十四条", "第九十九条")


def _law_refs(article: str) -> dict:
    return {
        "law_name": "劳动合同法",
        "article": article,
        "content": f"《劳动合同法》{article}相关条文内容。",
        "similarity": 0.92,
    }


@pytest.fixture(autouse=True)
def _multi_agent_mode(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "multi")


def _make_llm_fixture(reviewer_json: str = _REVIEWER_JSON):
    @pytest.fixture
    def _fake_llm(monkeypatch) -> None:
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
                return reviewer_json
            raise AssertionError(f"意外调用 LLM 的节点: {self.name}")

        monkeypatch.setattr(BaseAgent, "invoke_llm", fake_invoke)

    return _fake_llm


fake_llm = _make_llm_fixture()
fake_llm_bad = _make_llm_fixture(_REVIEWER_JSON_BAD)


@pytest.fixture
def fake_mcp(monkeypatch) -> None:
    async def fake_call(self: MCPClient, tool_name: str, **arguments: object) -> object:
        if tool_name == "law_search":
            return {"results": [_law_refs("第二十三条"), _law_refs("第二十四条")]}
        if tool_name == "negotiation":
            return {"negotiation_tip": "建议与 HR 沟通竞业限制补偿标准与违约金上限。"}
        raise AssertionError(f"意外调用 MCP 工具: {tool_name}")

    monkeypatch.setattr(MCPClient, "call", fake_call)


def _collect(agen: AsyncGenerator[SSEEvent, None]) -> list[SSEEvent]:
    async def _drain() -> list[SSEEvent]:
        return [event async for event in agen]

    return asyncio.run(_drain())


class TestMultiAgentTopology:
    def test_graph_has_supervisor_and_verifier(self) -> None:
        nodes = set(build_contract_graph("multi").get_graph().nodes.keys())
        assert {
            "coordinator", "extractor", "retriever",
            "reviewer", "verifier", "negotiator",
        } <= nodes

    def test_linear_graph_is_still_available(self) -> None:
        nodes = set(build_contract_graph("linear").get_graph().nodes.keys())
        assert "coordinator" not in nodes
        assert "verifier" not in nodes


class TestAgentCollaboration:
    def test_agents_communicate_via_message_bus(self, fake_llm, fake_mcp) -> None:
        graph = build_contract_graph("multi")
        raw = asyncio.run(
            graph.ainvoke(AgentState(contract_id="ma-1", raw_text=_CONTRACT_TEXT))
        )
        st = raw if isinstance(raw, AgentState) else AgentState(**raw)

        assert st.agent_trace == [
            "coordinator", "extractor", "retriever",
            "reviewer", "verifier", "negotiator",
        ]
        kinds = {m.kind for m in st.agent_messages}
        assert {"plan", "task", "result", "handoff"} <= kinds
        assert {m.recipient for m in st.agent_messages if m.kind == "task"} == set(st.agent_plan)
        assert any(m.sender == "coordinator" and m.kind == "plan" for m in st.agent_messages)
        assert any(m.sender == "verifier" and m.recipient == "negotiator" for m in st.agent_messages)
        assert st.verdict == "approve"
        assert st.review_rounds == 0
        assert len(st.risk_assessments) == 1
        assert st.risk_assessments[0].negotiation_tip

    def test_verifier_vetoes_and_triggers_one_rework(self, fake_llm_bad, fake_mcp) -> None:
        graph = build_contract_graph("multi")
        raw = asyncio.run(
            graph.ainvoke(AgentState(contract_id="ma-2", raw_text=_CONTRACT_TEXT))
        )
        st = raw if isinstance(raw, AgentState) else AgentState(**raw)

        assert st.agent_trace.count("reviewer") == 2  # 条件边退回重审
        assert st.agent_trace.count("verifier") == 2
        assert st.review_rounds == 1  # 受 max_review_rounds 约束, 不无限循环
        assert any(m.kind == "rework" and m.sender == "verifier" for m in st.agent_messages)
        assert st.verdict == "approve"  # 达上限后放行, 但问题留给人工复核
        assert any("无法溯源" in issue for issue in st.quality_issues)

    def test_short_text_skips_verifier_by_coordinator_decision(self, fake_llm, fake_mcp) -> None:
        graph = build_contract_graph("multi")
        raw = asyncio.run(
            graph.ainvoke(AgentState(contract_id="ma-3", raw_text="甲方与乙方签订劳动合同。"))
        )
        st = raw if isinstance(raw, AgentState) else AgentState(**raw)
        assert "verifier" not in st.agent_plan
        assert "verifier" not in st.agent_trace


class TestMultiAgentProtocol:
    def test_sse_timeline_and_summary(self, fake_llm, fake_mcp) -> None:
        events = _collect(run_contract_analysis(contract_id="ma-4", raw_text=_CONTRACT_TEXT))
        starts = [e for e in events if e.event == SSEEventType.NODE_START]
        completes = [e for e in events if e.event == SSEEventType.NODE_COMPLETE]

        assert [e.data["node_name"] for e in starts] == [
            "coordinator", "extractor", "retriever",
            "reviewer", "verifier", "negotiator",
        ]
        assert len(completes) == 6
        assert sum(e.event == SSEEventType.RISK_FOUND for e in events) == 1

        summary = next(e for e in events if e.event == SSEEventType.SUMMARY)
        assert summary.data["agent_mode"] == "multi"
        assert summary.data["overall_score"] == 45
        assert summary.data["review_rounds"] == 0
        assert events[-1].event == SSEEventType.COMPLETE

    def test_fail_loud_still_holds(self, monkeypatch, fake_llm, fake_mcp) -> None:
        async def broken_reviewer_run(self: ReviewerAgent, state: AgentState) -> AgentState:
            raise RuntimeError("审查引擎内部错误")

        monkeypatch.setattr(ReviewerAgent, "run", broken_reviewer_run)
        events = _collect(run_contract_analysis(contract_id="ma-5", raw_text=_CONTRACT_TEXT))
        seq = [e.event for e in events]
        assert seq[-1] == SSEEventType.ERROR
        assert SSEEventType.SUMMARY not in seq
        assert SSEEventType.COMPLETE not in seq
