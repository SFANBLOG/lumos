"""审查增强层回归测试 (纯逻辑, 不依赖 MySQL / Milvus / LLM / MinIO).

覆盖本次补齐的四项能力: 合同要素表、缺失条款检测、条款级 redline、
法规时效元数据，外加 SSE 序列化与带批注导出。
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.agent.contract_facts import (
    FACT_RULES,
    coverage_score,
    detect_missing_clauses,
    extract_contract_facts,
)
from app.agent.redline import REDLINE_LIBRARY, attach_redlines, build_revision
from app.agent.review_enrichment import enrich
from app.agent.state import AgentState, RiskAssessment
from app.api.v1.exports import _docx_bytes, _markdown
from app.models.analysis import RiskCategory, RiskLevel
from app.rag.law_corpus import ALL_LAWS
from app.rag.law_meta import active_laws, attach_metadata, is_effective, metadata_for
from app.schemas.analysis import AnalysisReportResponse, RiskItemResponse
from app.schemas.review import FACT_MISSING, FACT_PRESENT

_FULL_CONTRACT = """甲方：星辰科技有限公司
乙方：张三  身份证号：110101199001011234
一、合同期限：自 2026 年 1 月 1 日至 2028 年 12 月 31 日，固定期限劳动合同。
二、工作内容：乙方担任软件工程师，工作地点为上海市浦东新区。
三、工作时间：执行标准工时，每日工作 8 小时，依法享有带薪年休假。
四、劳动报酬：税前月薪 20000 元 / 月，每月 15 日发放工资。
五、社会保险：甲方自用工之日起依法缴纳五险一金。
六、劳动保护：甲方提供符合国家规定的劳动条件与劳动防护用品。
七、合同解除：乙方提前三十日书面通知甲方可解除劳动合同。
八、竞业限制：乙方离职后二年内不得从事竞争业务，甲方按月支付竞业补偿。
九、争议解决：由劳动合同履行地劳动争议仲裁委员会管辖。
"""


def test_fact_rules_have_unique_keys() -> None:
    keys = [rule.key for rule in FACT_RULES]
    assert len(keys) == len(set(keys))
    assert any(rule.required for rule in FACT_RULES)


def test_extract_facts_on_complete_contract() -> None:
    facts = extract_contract_facts(_FULL_CONTRACT)
    by_key = {f.key: f for f in facts}

    assert by_key["party_a"].status == FACT_PRESENT
    assert "星辰科技" in by_key["party_a"].value
    assert by_key["party_a"].evidence  # 必须保留原文定位
    assert by_key["party_a"].confidence > 0
    assert by_key["salary"].status == FACT_PRESENT
    assert by_key["social_insurance"].status == FACT_PRESENT
    assert by_key["work_location"].status == FACT_PRESENT
    assert detect_missing_clauses(facts) == []
    assert coverage_score(facts) == 100


def test_extract_facts_on_empty_contract_reports_all_required_gaps() -> None:
    facts = extract_contract_facts("")
    assert all(f.status == FACT_MISSING for f in facts)
    assert coverage_score(facts) == 0
    missing = detect_missing_clauses(facts)
    assert len(missing) == sum(1 for rule in FACT_RULES if rule.required)
    assert all(m.suggested_text for m in missing), "每条缺口都要给可直接使用的补充措辞"
    assert all(m.legal_basis for m in missing)


def test_missing_clauses_cover_statutory_article_17() -> None:
    facts = extract_contract_facts("甲方：测试公司\n")
    missing = {m.key for m in detect_missing_clauses(facts)}
    for key in ("party_b", "contract_term", "work_location", "salary", "social_insurance"):
        assert key in missing
    article_17 = next(
        m for m in detect_missing_clauses(facts) if m.key == "work_location"
    )
    assert "第十七条" in article_17.legal_basis


def test_coverage_score_is_bounded() -> None:
    facts = extract_contract_facts(_FULL_CONTRACT)
    assert 0 <= coverage_score(facts) <= 100


def test_redline_library_covers_every_risk_category() -> None:
    for category in RiskCategory:
        assert category.value in REDLINE_LIBRARY
        rule = build_revision(category.value)
        assert rule.suggested and rule.reason and rule.legal_basis
    assert build_revision("unknown_category").suggested  # 通用兜底


def test_attach_redlines_fills_without_overwriting() -> None:
    risks = [
        RiskAssessment(
            category=RiskCategory.NON_COMPETE,
            level=RiskLevel.HIGH,
            title="竞业补偿过低",
            original_clause="竞业限制两年",
            explanation="补偿过低",
            legal_basis="《劳动合同法》第二十三条",
            negotiation_tip="与 HR 沟通",
            score=30,
        ),
        RiskAssessment(
            category=RiskCategory.RESIGNATION,
            level=RiskLevel.MEDIUM,
            title="离职需审批",
            original_clause="离职需批准",
            explanation="限制解除权",
            legal_basis="《劳动合同法》第三十七条",
            negotiation_tip="沟通",
            suggested_revision="已有的人工改写文本",
            score=40,
        ),
    ]
    assert attach_redlines(risks) == 1
    assert "经济补偿" in risks[0].suggested_revision
    assert risks[1].suggested_revision == "已有的人工改写文本"
    assert attach_redlines(risks) == 0


def test_enrich_populates_state_and_summary_is_json_serializable() -> None:
    state = AgentState(contract_id="c-1", raw_text="甲方：星辰科技有限公司\n")
    state.risk_assessments = [
        RiskAssessment(
            category=RiskCategory.PROBATION_SALARY,
            level=RiskLevel.HIGH,
            title="试用期工资过低",
            original_clause="试用期工资 60%",
            explanation="低于法定下限",
            legal_basis="《劳动合同法》第二十条",
            negotiation_tip="沟通",
            score=25,
        )
    ]
    enrich(state)

    assert len(state.contract_fact_items) == len(FACT_RULES)
    assert state.missing_clauses
    assert 0 < state.coverage_score < 100
    assert state.risk_assessments[0].suggested_revision
    # SSE 侧是 json.dumps(event.data), 必须保证嵌套模型已转成纯 dict
    payload = {
        "contract_fact_items": [f.model_dump() for f in state.contract_fact_items],
        "missing_clauses": [m.model_dump() for m in state.missing_clauses],
        "coverage_score": state.coverage_score,
    }
    json.dumps(payload, ensure_ascii=False)


def test_report_schema_exposes_new_fields() -> None:
    report = AnalysisReportResponse(
        contract_id="c-1",
        overall_score=60,
        overall_level=RiskLevel.MEDIUM,
        summary="测试",
        analyzed_at=datetime.now(UTC),
    )
    assert report.contract_facts == []
    assert report.missing_clauses == []
    assert report.coverage_score == 100

    item = RiskItemResponse(
        category=RiskCategory.NON_COMPETE,
        level=RiskLevel.HIGH,
        title="测试",
        explanation="说明",
        score=30,
    )
    assert item.suggested_revision == ""


def test_law_metadata_is_injected_into_corpus() -> None:
    assert ALL_LAWS, "法条语料不应为空"
    required = {"effective_from", "effective_until", "region", "version", "source_url"}
    for law in ALL_LAWS:
        assert required.issubset(law.keys()), law.get("law_name")
    assert metadata_for("劳动合同法").effective_from == "2013-07-01"
    assert metadata_for("最低工资规定").region != "全国"


def test_effective_filter_drops_future_and_expired_laws() -> None:
    today = date(2026, 11, 9)
    laws = [
        {"law_name": "现行法", "effective_from": "2008-01-01", "effective_until": ""},
        {"law_name": "已废止", "effective_from": "1990-01-01", "effective_until": "2020-12-31"},
        {"law_name": "未生效", "effective_from": "2030-01-01", "effective_until": ""},
    ]
    for law in laws:
        attach_metadata(law)
    kept = {law["law_name"] for law in active_laws(laws, today)}
    assert kept == {"现行法"}
    assert is_effective(laws[0], today) is True
    assert is_effective(laws[1], today) is False
    assert is_effective({"effective_from": "不是日期"}, today) is True  # 元数据异常不误删


def _fake_report_objects():
    analysis = SimpleNamespace(
        overall_score=45,
        overall_level=SimpleNamespace(value="high"),
        summary="存在竞业与工资条款风险",
        created_at=datetime(2026, 11, 9, tzinfo=UTC),
    )
    risks = [
        SimpleNamespace(
            title="竞业补偿过低",
            level=SimpleNamespace(value="high"),
            score=30,
            original_clause="竞业限制两年",
            explanation="补偿过低",
            legal_basis="《劳动合同法》第二十三条",
            suggested_revision="竞业限制期限不超过二年，按月支付补偿。",
            negotiation_tip="与 HR 沟通",
        )
    ]
    facts = [
        SimpleNamespace(
            label="劳动报酬数额",
            status=FACT_PRESENT,
            value="20000 元/月",
            evidence="税前月薪 20000 元/月",
            confidence=0.9,
            required=True,
        )
    ]
    missing = [
        SimpleNamespace(
            label="社会保险",
            level="high",
            reason="法定必备条款",
            legal_basis="《社会保险法》第五十八条",
            suggested_text="应依法足额缴纳五险。",
        )
    ]
    return analysis, risks, facts, missing


def test_markdown_export_contains_redline_and_missing_clause() -> None:
    text = _markdown("contract-0001", *_fake_report_objects())
    assert "建议改为" in text
    assert "缺失条款与建议补充措辞" in text
    assert "合同要素核对表" in text
    assert "不构成具有法定效力的专业法律意见" in text


def test_docx_export_is_a_real_zip_document() -> None:
    data = _docx_bytes("contract-0001", *_fake_report_objects())
    assert data[:2] == b"PK", "python-docx 应产出 .docx (zip) 字节流"
    assert len(data) > 2000


def test_workflow_summary_and_risk_events_carry_enhancements(monkeypatch) -> None:
    """端到端串一次线性图: SSE 的 SUMMARY / RISK_FOUND 都能被 json.dumps 且带增强字段."""
    import asyncio

    from app.agent.base import BaseAgent
    from app.agent.graph import run_contract_analysis
    from app.mcp.client import MCPClient
    from app.schemas.analysis import SSEEventType

    monkeypatch.setenv("AGENT_MODE", "linear")
    raw_text = "甲方：测试公司\n一、竞业限制：竞业限制两年，补偿 1000 元。"

    async def fake_invoke(self, user_message, *, temperature=None, max_tokens=4096):
        if self.name == "extractor":
            return '[{"clause_index": 1, "title": "竞业限制", "content": "竞业限制两年，补偿 1000 元。", "category": "non_compete"}]'
        if self.name == "reviewer":
            return json.dumps(
                {
                    "risks": [
                        {
                            "category": "non_compete",
                            "level": "high",
                            "title": "竞业补偿过低",
                            "original_clause": "竞业限制两年，补偿 1000 元。",
                            "explanation": "补偿明显偏低",
                            "legal_basis": "《劳动合同法》第二十三条",
                            "score": 30,
                        }
                    ],
                    "overall_score": 45,
                    "overall_level": "high",
                    "summary": "存在竞业条款风险",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"意外调用 LLM 的节点: {self.name}")

    async def fake_call(self, tool_name, **kwargs):
        if tool_name == "law_search":
            return {
                "results": [
                    {
                        "law_name": "劳动合同法",
                        "article": "第二十三条",
                        "content": "竞业限制相关条文",
                        "similarity": 0.9,
                    }
                ]
            }
        if tool_name == "negotiation":
            return {"negotiation_tip": "建议与 HR 沟通补偿标准"}
        raise AssertionError(f"意外调用 MCP 工具: {tool_name}")

    monkeypatch.setattr(BaseAgent, "invoke_llm", fake_invoke)
    monkeypatch.setattr(MCPClient, "call", fake_call)

    async def drain():
        return [e async for e in run_contract_analysis("c-integration", raw_text)]

    events = asyncio.run(drain())
    summary = next(e.data for e in events if e.event == SSEEventType.SUMMARY)
    # SSE 端点直接用 json.dumps(event.data), 必须不出现 pydantic 对象
    json.dumps(summary, ensure_ascii=False)

    assert len(summary["contract_fact_items"]) == len(FACT_RULES)
    assert summary["missing_clauses"], "极简合同应检出缺失必备条款"
    assert 0 < summary["coverage_score"] < 100
    assert summary["agent_mode"] == "linear"

    risk_events = [e for e in events if e.event == SSEEventType.RISK_FOUND]
    assert risk_events
    assert risk_events[0].data["suggested_revision"], "RISK_FOUND 也应带 redline"
