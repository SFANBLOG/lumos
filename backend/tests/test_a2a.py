"""
A2A (Agent2Agent Protocol) 集成测试.

通过 mock Lumos 合同审查工作流 (run_contract_analysis), 仅验证 A2A
协议适配层: Agent Card 生成、JSON-RPC 同步端点、SSE 流式端点,
不触发真实 LLM / 向量库调用。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.a2a.agent_card import A2A_PROTOCOL_VERSION, get_agent_card
from app.a2a.models import TaskState
from app.schemas.analysis import SSEEvent, SSEEventType


# ─── fixture: 最小 app (仅挂载 a2a 路由, 避免完整 lifespan 下载模型) ──


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # 用一段假的审查事件流替换真实工作流
    async def fake_run(contract_id: str, raw_text: str, session=None):
        yield SSEEvent(
            event=SSEEventType.RISK_FOUND,
            data={
                "category": "竞业限制",
                "level": "high",
                "title": "竞业禁止范围过宽",
                "original_clause": "离职后 3 年内不得从事任何相关工作",
                "explanation": "竞业限制应限于有竞争关系的原单位业务, 且期限不得超过 2 年。",
                "legal_basis": "《劳动合同法》第二十四条",
                "negotiation_tip": "可要求将范围限定为直接竞争业务, 并缩短至 1 年。",
                "score": 40,
            },
        )
        yield SSEEvent(
            event=SSEEventType.SUMMARY,
            data={
                "overall_score": 60,
                "overall_level": "medium",
                "summary": "合同存在 1 处较高风险条款, 建议协商修改。",
                "total_clauses": 1,
                "total_risks": 1,
                "legal_references_count": 1,
                "confidence_score": 100,
                "quality_issues": [],
                "contract_facts": {},
            },
        )
        yield SSEEvent(event=SSEEventType.COMPLETE, data={"message": "完成"})

    monkeypatch.setattr("app.a2a.executor.run_contract_analysis", fake_run)

    app = FastAPI()
    from app.a2a.routes import router

    app.include_router(router)
    return TestClient(app)


def _send_payload(text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }


# ─── Agent Card ──────────────────────────────────────────────────


def test_agent_card_structure():
    card = get_agent_card()
    assert card.protocolVersion == A2A_PROTOCOL_VERSION
    assert card.capabilities.streaming is True
    assert card.url.endswith("/a2a")
    assert len(card.skills) >= 1
    assert card.skills[0].id == "contract-risk-review"


def test_agent_card_endpoint(client: TestClient):
    resp = client.get("/.well-known/agent.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"]
    assert any(s["id"] == "contract-risk-review" for s in data["skills"])
    assert data["capabilities"]["streaming"] is True


# ─── 同步 JSON-RPC (message/send) ───────────────────────────────


def test_a2a_send_sync(client: TestClient):
    resp = client.post("/a2a", json=_send_payload("这是一份劳动合同正文……"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert "result" in body
    task = body["result"]
    assert task["status"]["state"] == TaskState.COMPLETED.value
    assert task["artifacts"]
    risks_artifact = next(a for a in task["artifacts"] if a["name"] == "risk_assessments")
    risks = risks_artifact["parts"][0]["data"]["risks"]
    assert len(risks) == 1
    assert risks[0]["title"] == "竞业禁止范围过宽"


def test_a2a_send_empty_text(client: TestClient):
    resp = client.post("/a2a", json=_send_payload("   "))
    body = resp.json()
    assert body["result"]["status"]["state"] == TaskState.FAILED.value


def test_a2a_unknown_method(client: TestClient):
    resp = client.post(
        "/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "foo/bar", "params": {}}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == -32601


def test_a2a_invalid_json(client: TestClient):
    resp = client.post("/a2a", content=b"not-json", headers={"content-type": "application/json"})
    assert resp.status_code == 400


# ─── 流式 SSE (message/stream) ──────────────────────────────────


def test_a2a_stream(client: TestClient):
    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "message/stream",
        "params": {
            "message": {"role": "user", "parts": [{"kind": "text", "text": "合同正文"}]}
        },
    }
    resp = client.post("/a2a/stream", json=payload)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events: list[dict] = []
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:") :].strip()))

    assert events, "应有 SSE 事件"
    # 最后一条应为终态 completed
    last = events[-1]["result"]
    assert last["kind"] == "status-update"
    assert last["final"] is True
    assert last["status"]["state"] == TaskState.COMPLETED.value
    # 中间应出现 artifact-update 携带风险清单
    artifact_events = [e["result"] for e in events if e["result"].get("kind") == "artifact-update"]
    assert any(
        a["artifact"]["name"] == "risk_assessments" for a in artifact_events
    )
