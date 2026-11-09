"""合同级端到端评测框架的指标回归测试.

重点验证: 这不是检索层 hit@k，而是条款级 P/R/F1 + 等级一致性 + 严重漏报数,
且能区分单风险与多风险混合合同。
"""

from __future__ import annotations

import json

from eval.review_eval import (
    GoldenCase,
    GoldenRisk,
    PredictedCase,
    PredictedRisk,
    evaluate,
    load_goldens,
    load_predictions,
    match_case,
    predictions_from_report,
)


def _golden() -> GoldenCase:
    return GoldenCase(
        contract_id="c-1",
        group="single",
        risks=(
            GoldenRisk("non_compete", "high", "竞业限制两年", required=True),
            GoldenRisk("probation_salary", "medium", "试用期工资 60%"),
        ),
        missing_clauses=("social_insurance", "work_location"),
    )


def _perfect() -> PredictedCase:
    return PredictedCase(
        contract_id="c-1",
        risks=(
            PredictedRisk("non_compete", "high", "竞业限制两年，补偿 1000 元"),
            PredictedRisk("probation_salary", "medium", "试用期工资 60% 发放"),
        ),
        missing_clauses=("social_insurance", "work_location"),
    )


def test_perfect_prediction_scores_one() -> None:
    row = match_case(_golden(), _perfect())
    assert (row["precision"], row["recall"], row["f1"]) == (1.0, 1.0, 1.0)
    assert row["level_agreement"] == 1.0
    assert row["severe_misses"] == 0
    assert row["missing_metrics"]["f1"] == 1.0


def test_false_positive_lowers_precision_but_not_recall() -> None:
    predicted = PredictedCase(
        contract_id="c-1",
        risks=(
            *_perfect().risks,
            PredictedRisk("jurisdiction", "low", "管辖地争议"),
        ),
        missing_clauses=_perfect().missing_clauses,
    )
    row = match_case(_golden(), predicted)
    assert row["recall"] == 1.0
    assert row["precision"] < 1.0
    assert row["fp"] == 1


def test_missing_high_risk_is_counted_as_severe() -> None:
    predicted = PredictedCase(
        contract_id="c-1",
        risks=(_perfect().risks[1],),
        missing_clauses=("social_insurance",),
    )
    row = match_case(_golden(), predicted)
    assert row["fn"] == 1
    assert row["severe_misses"] == 1
    assert row["missed_categories"] == ["non_compete"]
    assert row["missing_metrics"]["recall"] == 0.5


def test_level_mismatch_lowers_level_agreement() -> None:
    predicted = PredictedCase(
        contract_id="c-1",
        risks=(
            PredictedRisk("non_compete", "low", "竞业限制两年"),
            PredictedRisk("probation_salary", "medium", "试用期工资 60%"),
        ),
        missing_clauses=_perfect().missing_clauses,
    )
    row = match_case(_golden(), predicted)
    assert row["recall"] == 1.0
    assert row["level_agreement"] == 0.5


def test_evaluate_splits_single_and_mixed_groups() -> None:
    mixed = GoldenCase(
        contract_id="c-2",
        group="mixed",
        risks=(GoldenRisk("resignation", "high", "离职需审批", required=True),),
    )
    mixed_pred = PredictedCase(
        contract_id="c-2",
        risks=(PredictedRisk("resignation", "high", "离职需审批，经批准方可解除劳动合同"),),
    )
    result = evaluate([_golden(), mixed], [_perfect(), mixed_pred])
    assert result["golden_count"] == 2
    assert set(result["by_group"]) == {"mixed", "single"}
    assert result["overall"]["tp"] == 3
    assert result["overall"]["severe_misses"] == 0
    assert result["unmatched_predictions"] == []
    assert "hit@k" in result["disclaimer"]


def test_predictions_from_report_adapts_api_response() -> None:
    report = {
        "contract_id": "c-3",
        "risk_items": [
            {
                "category": "non_compete",
                "level": "high",
                "original_clause": "竞业限制两年",
            }
        ],
        "missing_clauses": [{"key": "salary"}],
    }
    predicted = predictions_from_report(report)
    assert predicted.contract_id == "c-3"
    assert predicted.risks[0].category == "non_compete"
    assert predicted.missing_clauses == ("salary",)


def test_cli_loaders_round_trip(tmp_path) -> None:
    golden_file = tmp_path / "golden.json"
    pred_file = tmp_path / "pred.json"
    golden_file.write_text(
        json.dumps(
            [
                {
                    "contract_id": "c-1",
                    "group": "single",
                    "risks": [{"category": "non_compete", "level": "high"}],
                    "missing_clauses": ["salary"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    pred_file.write_text(
        json.dumps(
            [
                {
                    "contract_id": "c-1",
                    "risk_items": [
                        {"category": "non_compete", "level": "high", "original_clause": "x"}
                    ],
                    "missing_clauses": [{"key": "salary"}],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = evaluate(load_goldens(golden_file), load_predictions(pred_file))
    assert result["overall"]["f1"] == 1.0


def test_similar_clause_snippet_tolerates_ocr_differences() -> None:
    golden = GoldenCase(
        contract_id="c-9",
        risks=(GoldenRisk("resignation", "high", "离职需审批", required=True),),
    )
    predicted = PredictedCase(
        contract_id="c-9",
        risks=(PredictedRisk("resignation", "high", "离职需批准方可解除"),),
    )
    assert match_case(golden, predicted)["recall"] == 1.0

    # 相似度兜底只在同类别生效, 跨类别仍算误报
    wrong = PredictedCase(
        contract_id="c-9",
        risks=(PredictedRisk("jurisdiction", "high", "离职需批准方可解除"),),
    )
    assert match_case(golden, wrong)["recall"] == 0.0
