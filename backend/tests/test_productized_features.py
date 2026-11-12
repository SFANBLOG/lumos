"""7 项「半成品 → 完整产品」的回归测试.

全部为纯逻辑测试: 不依赖 MySQL / Milvus / MinIO / LLM / 浏览器。
覆盖逐条改写、语义级要素、法规元数据核验、评测门禁、反馈回流、
PDF/分享/批注，以及金标准生成。
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.contract_facts import (
    coverage_score,
    detect_missing_clauses,
    extract_contract_facts,
)
from app.agent.fact_semantics import infer_contract_type, rules_for
from app.agent.redline_engine import attach_rewrites, build_rewrite
from app.agent.state import RiskAssessment
from app.api.v1.exports import _markdown, _pdf_bytes, render_export
from app.api.v1.sharing import _expired, hash_token
from app.models.analysis import RiskCategory, RiskLevel
from app.rag.law_meta import (
    active_laws,
    attach_metadata,
    metadata_diff,
    reload_overrides,
    snapshot,
    verify_laws,
)
from app.schemas.review import FACT_CONTRADICTED, FACT_MISSING, FACT_PRESENT
from app.services.feedback_insights import build_eval_cases, rule_tuning_suggestions
from eval.build_goldens import build_goldens
from eval.review_eval import (
    DEFAULT_GATE_FILE,
    GoldenCase,
    GoldenRisk,
    PredictedCase,
    PredictedRisk,
    check_gate,
    evaluate,
    load_thresholds,
)


class _Enum:
    def __init__(self, value: str) -> None:
        self.value = value


# ─── 模块 1: 逐条 redline ──────────────────────────────────────


def _risk(**kwargs) -> RiskAssessment:
    params = dict(
        category=RiskCategory.NON_COMPETE,
        level=RiskLevel.HIGH,
        title="竞业补偿过低",
        original_clause="乙方离职后二年内不得从事竞争业务，甲方一次性支付补偿 1000 元。",
        explanation="补偿明显偏低且未按月支付",
        legal_basis="《劳动合同法》第二十三条",
        negotiation_tip="与 HR 沟通",
        score=30,
    )
    params.update(kwargs)
    return RiskAssessment(**params)


def test_llm_rewrite_is_adopted_with_diff_and_audit_fields() -> None:
    risk = _risk(
        llm_revised_clause="乙方离职后竞业限制期限不超过二年，甲方应按月支付竞业限制经济补偿。",
        llm_rewrite_reason="原条款一次性支付且金额过低，不符合按月支付补偿的要求。",
    )
    assert attach_rewrites([risk]) == (1, 0)
    assert risk.revision_method == "llm"
    assert risk.revision_confidence == 0.9
    assert "按月支付" in risk.suggested_revision
    assert "---" in risk.revision_diff and "+++" in risk.revision_diff
    assert "按月支付" in risk.revision_reason
    assert attach_rewrites([risk]) == (0, 0), "重复执行应幂等"


def test_invalid_llm_rewrite_falls_back_to_this_clause() -> None:
    rewrite = build_rewrite(
        original="乙方自愿放弃社保，甲方不予缴纳。",
        category="probation_insurance",
        llm_revised="{not a clause}",
        llm_reason="",
    )
    assert rewrite.method == "rule"
    assert rewrite.diff
    assert rewrite.reason


def test_manual_revision_is_not_overwritten() -> None:
    risk = _risk(suggested_revision="法务人工改写的条款文本")
    assert attach_rewrites([risk]) == (0, 0)
    assert risk.suggested_revision == "法务人工改写的条款文本"


# ─── 模块 2: 语义级要素检测 ───────────────────────────────────


def test_contradictory_clause_is_not_counted_as_compliant() -> None:
    text = (
        "劳动合同\n甲方：测试公司\n乙方：张三 身份证号：110101199001011234\n"
        "社会保险：乙方自愿放弃社保，甲方以补贴代替。\n"
    )
    facts = extract_contract_facts(text)
    insurance = next(f for f in facts if f.key == "social_insurance")
    assert insurance.status == FACT_CONTRADICTED
    assert insurance.matched_by == "negation"
    assert insurance.contradiction
    assert insurance.confidence >= 0.9
    assert all(f.rule_set == "labor_contract" for f in facts)
    missing = {m.key: m for m in detect_missing_clauses(facts)}
    assert "social_insurance" in missing
    assert missing["social_insurance"].level == "high"
    assert coverage_score(facts) < 100


def test_rule_set_switches_by_contract_type() -> None:
    text = "技术服务合同\n委托方：云启数据有限公司\n受托方：智联软件工作室\n"
    facts = extract_contract_facts(text, contract_type="service_contract")
    keys = {f.key for f in facts}
    assert "service_scope" in keys and "liability" in keys
    assert "social_insurance" not in keys
    assert len(facts) == len(rules_for("service_contract"))
    assert all(f.status == FACT_MISSING or f.status == FACT_PRESENT for f in facts)
    assert {m.key for m in detect_missing_clauses(facts)} & {"liability"}


def test_contract_type_inference_is_conservative() -> None:
    assert infer_contract_type("劳动合同 甲方：测试公司") == "labor_contract"
    assert infer_contract_type("保密协议 甲方：测试公司") == "nda"
    assert infer_contract_type("技术服务合同 委托方：A 受托方：B") == "service_contract"
    # 劳动合同里的竞业条款不应把整份合同误判成 NDA
    assert infer_contract_type("劳动合同 甲方：测试公司\n八、竞业限制：两年") == "labor_contract"


# ─── 模块 3: 法规时效元数据可核验 ─────────────────────────────


def test_baseline_metadata_is_flagged_as_unverified() -> None:
    law = {"law_name": "劳动合同法", "article": "第二十三条"}
    attach_metadata(law)
    report = verify_laws([law], as_of=date(2026, 11, 11))
    codes = {issue["code"] for issue in report["issues"]}
    assert report["ok"] is False
    assert {"source_not_verified", "never_checked", "baseline_value"} <= codes


def test_external_override_makes_metadata_verifiable(monkeypatch, tmp_path) -> None:
    override = tmp_path / "overrides.json"
    override.write_text(
        json.dumps(
            {
                "劳动合同法": {
                    "source_url": "https://flk.npc.gov.cn/detail2.html?law=labour-contract",
                    "checked_at": "2026-11-10",
                    "note": "已按国家法律法规数据库核对",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LUMOS_LAW_META_PATH", str(override))
    reload_overrides()
    law = {"law_name": "劳动合同法", "article": "第二十三条"}
    attach_metadata(law)
    assert law["checked_at"] == "2026-11-10"
    assert verify_laws([law], as_of=date(2026, 11, 11))["ok"] is True
    monkeypatch.delenv("LUMOS_LAW_META_PATH")
    reload_overrides()


def test_region_filter_and_metadata_diff() -> None:
    laws = [
        {"law_name": "全国法", "effective_from": "2008-01-01", "region": "全国"},
        {"law_name": "上海口径", "effective_from": "2008-01-01", "region": "上海市"},
        {"law_name": "北京口径", "effective_from": "2008-01-01", "region": "北京市"},
        {"law_name": "已废止", "effective_from": "1990-01-01", "effective_until": "2020-12-31", "region": "全国"},
    ]
    kept = {l["law_name"] for l in active_laws(laws, date(2026, 11, 11), region="上海市")}
    assert kept == {"全国法", "上海口径"}
    previous = snapshot(laws)
    laws[1]["region"] = "上海市 (2026 修订)"
    changes = metadata_diff(previous, snapshot(laws))
    assert any(c["law_name"] == "上海口径" and c["field"] == "region" for c in changes)


# ─── 模块 4: 金标准与发布门禁 ─────────────────────────────────


def test_goldens_can_be_built_from_annotated_contracts() -> None:
    root = Path(__file__).resolve().parents[1] / "eval" / "goldens"
    cases = json.loads((root / "contracts.json").read_text(encoding="utf-8"))
    goldens = build_goldens(cases)
    assert len(goldens) == 5
    assert sum(len(g["risks"]) for g in goldens) == 5
    assert any(g["contract_type"] == "service_contract" for g in goldens)
    assert all(g["missing_clauses"] == [] or isinstance(g["missing_clauses"], list) for g in goldens)


def test_release_gate_passes_on_perfect_predictions_and_blocks_severe_miss() -> None:
    goldens = [
        GoldenCase(
            contract_id="c-1",
            risks=(GoldenRisk("non_compete", "high", "补偿 500 元"),),
            missing_clauses=("salary",),
        )
    ]
    predictions = [
        PredictedCase(
            contract_id="c-1",
            risks=(PredictedRisk("non_compete", "high", "补偿 500 元"),),
            missing_clauses=("salary",),
        )
    ]
    thresholds = load_thresholds(DEFAULT_GATE_FILE)
    assert check_gate(evaluate(goldens, predictions), thresholds)["passed"] is True
    failed = check_gate(evaluate(goldens, []), thresholds)
    assert failed["passed"] is False
    assert {v["metric"] for v in failed["violations"]} >= {"severe_misses", "recall"}


# ─── 模块 5: 反馈回流 ─────────────────────────────────────────


def _feedback_rows():
    return [
        SimpleNamespace(id="f1", risk_item_id="r1", contract_id="c-1", verdict="false_positive", comment="不是风险"),
        SimpleNamespace(id="f2", risk_item_id="r2", contract_id="c-1", verdict="accepted", comment="确认"),
        SimpleNamespace(id="f3", risk_item_id="r3", contract_id="c-1", verdict="false_positive", comment="误报"),
        SimpleNamespace(id="f4", risk_item_id="r4", contract_id="c-1", verdict="false_positive", comment="误报"),
        SimpleNamespace(id="f5", risk_item_id="r5", contract_id="c-1", verdict="ignored", comment="先不管"),
    ]


def _risk_rows():
    return [
        SimpleNamespace(id=f"r{i}", category=_Enum("non_compete"), level=_Enum("high"), original_clause=f"竞业条款 {i}")
        for i in range(1, 6)
    ]


def test_feedback_exports_positive_goldens_and_negative_cases() -> None:
    result = build_eval_cases(_feedback_rows(), _risk_rows())
    assert result["negative_case_count"] == 3
    assert result["positive_risk_count"] == 1
    golden = result["goldens"][0]
    assert golden["risks"][0]["category"] == "non_compete"
    assert golden["risks"][0]["required"] is True
    assert result["negative_cases"][0]["expected_risks"] == []


def test_tuning_suggestions_give_actionable_steps() -> None:
    result = rule_tuning_suggestions(
        _feedback_rows(), _risk_rows(), min_samples=3, fp_threshold=0.3
    )
    assert result["suggestion_count"] == 1
    suggestion = result["suggestions"][0]
    assert suggestion["category"] == "non_compete"
    assert suggestion["false_positive_rate"] == 0.75
    assert suggestion["priority"] == "high"
    assert any("Reviewer prompt" in action for action in suggestion["actions"])


# ─── 模块 6: PDF / 分享 / 批注 ─────────────────────────────────


def _report_objects():
    analysis = SimpleNamespace(
        overall_score=45,
        overall_level=_Enum("high"),
        summary="存在竞业与社保条款风险",
        created_at=datetime(2026, 11, 11, tzinfo=UTC),
    )
    risks = [
        SimpleNamespace(
            title="竞业补偿过低",
            level=_Enum("high"),
            score=30,
            original_clause="竞业限制两年，补偿 1000 元。",
            explanation="补偿过低",
            legal_basis="《劳动合同法》第二十三条",
            suggested_revision="竞业限制不超过二年，按月支付补偿。",
            negotiation_tip="与 HR 沟通",
            revision_reason="原条款未按月支付",
            revision_method="llm",
            revision_diff="--- 原条款\n+++ 建议条款\n-一次性支付\n+按月支付",
            revision_confidence=0.9,
        )
    ]
    facts = [
        SimpleNamespace(
            label="社会保险",
            status="contradicted",
            value="自愿放弃社保",
            evidence="乙方自愿放弃社保",
            confidence=0.92,
            required=True,
            contradiction="自愿放弃社保",
        )
    ]
    missing = [
        SimpleNamespace(
            label="工作地点",
            level="medium",
            reason="法定必备条款",
            legal_basis="《劳动合同法》第十七条",
            suggested_text="应写明具体城市与办公地址。",
        )
    ]
    return analysis, risks, facts, missing


def test_pdf_export_is_a_real_pdf() -> None:
    data = _pdf_bytes("contract-0001", *_report_objects())
    assert data.startswith(b"%PDF")
    assert len(data) > 2000


def test_render_export_supports_pdf_and_rejects_unknown() -> None:
    content, mime, filename = render_export("pdf", "contract-0001", *_report_objects())
    assert content.startswith(b"%PDF")
    assert mime == "application/pdf"
    assert filename.endswith(".pdf")
    with pytest.raises(Exception):
        render_export("xlsx", "contract-0001", *_report_objects())


def test_markdown_contains_rewrite_audit_and_annotations() -> None:
    annotations = [
        SimpleNamespace(author="法务-陈", comment="请核对补偿标准", quote="补偿 1000 元")
    ]
    text = _markdown("contract-0001", *_report_objects(), annotations)
    assert "改写理由" in text
    assert "改写来源" in text
    assert "在线批注" in text
    assert "法务-陈" in text


def test_share_token_hashing_and_expiry() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
    now = datetime.now(UTC)
    assert _expired(now - timedelta(hours=1), now) is True
    assert _expired(now + timedelta(hours=1), now) is False
    assert _expired((now + timedelta(hours=1)).replace(tzinfo=None), now) is False
