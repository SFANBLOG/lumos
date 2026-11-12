"""合同级端到端审查效果评测.

原项目只有 ``eval/retrieval_eval.py``（检索层 hit@k / MRR），且设计文档明确
写了「无端到端准确率评测」。``hit@5`` 是检索命中率，**不是审查准确率**。

本模块提供合同级金标准与指标:
- 条款级 precision / recall / F1（按风险类别 + 原文片段匹配）;
- 等级一致性 (matched pairs 中 level 相同的比例);
- **严重漏报数** (required 且 high 的金标准未被检出);
- 缺失条款检测 precision / recall / F1（按要素 key 集合）;
- 按 single / mixed 分组统计，避免多风险合同被单标签金标准掩盖。

用法::

    python -m eval.review_eval \
        --goldens eval/goldens/review_golden.json \
        --predictions eval/output/review_predictions.json \
        --out eval/output/review_metrics.json

预测集可以直接由报告接口响应生成，见 ``predictions_from_report``。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GoldenRisk:
    """一条人工标注的应有风险."""

    category: str
    level: str
    clause_snippet: str = ""
    required: bool = True


@dataclass(frozen=True)
class GoldenCase:
    """一份合同级金标准."""

    contract_id: str
    group: str = "single"  # single | mixed
    risks: tuple[GoldenRisk, ...] = ()
    missing_clauses: tuple[str, ...] = ()


@dataclass(frozen=True)
class PredictedRisk:
    """系统输出的一条风险."""

    category: str
    level: str
    original_clause: str = ""


@dataclass(frozen=True)
class PredictedCase:
    """系统对一份合同的完整输出."""

    contract_id: str
    risks: tuple[PredictedRisk, ...] = ()
    missing_clauses: tuple[str, ...] = ()


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


#: OCR 错字 / 断句 / 标点差异导致片段不完全相同时的相似度下限
_SNIPPET_SIMILARITY = 0.55


def _risk_hit(golden: GoldenRisk, predicted: PredictedRisk) -> bool:
    """类别一致且原文片段可互相定位才算命中.

    先做包含匹配; 不完全一致时用字符级相似度兜底 (仅限同类别,
    避免跨类别误匹配把误报算成命中)。
    """
    if golden.category != predicted.category:
        return False
    snippet = golden.clause_snippet.strip()
    if not snippet:
        return True
    original = predicted.original_clause.strip()
    if not original:
        return False
    if snippet in original or original in snippet:
        return True
    from difflib import SequenceMatcher

    return SequenceMatcher(None, snippet, original).ratio() >= _SNIPPET_SIMILARITY


def match_case(golden: GoldenCase, predicted: PredictedCase) -> dict[str, Any]:
    """单份合同的匹配明细 (贪心一对一匹配, 避免一条预测命中多条金标准)."""
    used: set[int] = set()
    matched_pairs: list[tuple[GoldenRisk, PredictedRisk]] = []
    missed: list[GoldenRisk] = []

    for g in golden.risks:
        hit = next(
            (
                i
                for i, p in enumerate(predicted.risks)
                if i not in used and _risk_hit(g, p)
            ),
            None,
        )
        if hit is None:
            missed.append(g)
        else:
            used.add(hit)
            matched_pairs.append((g, predicted.risks[hit]))

    tp = len(matched_pairs)
    fp = len(predicted.risks) - tp
    fn = len(missed)
    level_match = sum(1 for g, p in matched_pairs if g.level == p.level)

    g_missing = set(golden.missing_clauses)
    p_missing = set(predicted.missing_clauses)
    m_tp = len(g_missing & p_missing)
    m_fp = len(p_missing - g_missing)
    m_fn = len(g_missing - p_missing)

    return {
        "contract_id": golden.contract_id,
        "group": golden.group,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        **_prf(tp, fp, fn),
        "level_agreement": round(level_match / tp, 4) if tp else 0.0,
        "severe_misses": sum(
            1 for g in missed if g.required and g.level == "high"
        ),
        "missed_categories": [g.category for g in missed],
        "missing_tp": m_tp,
        "missing_fp": m_fp,
        "missing_fn": m_fn,
        "missing_metrics": _prf(m_tp, m_fp, m_fn),
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    m_tp = sum(r["missing_tp"] for r in rows)
    m_fp = sum(r["missing_fp"] for r in rows)
    m_fn = sum(r["missing_fn"] for r in rows)
    level_matched = sum(round(r["level_agreement"] * r["tp"]) for r in rows)
    return {
        "cases": len(rows),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        **_prf(tp, fp, fn),
        "level_agreement": round(level_matched / tp, 4) if tp else 0.0,
        "severe_misses": sum(r["severe_misses"] for r in rows),
        "missing_metrics": _prf(m_tp, m_fp, m_fn),
    }


def evaluate(
    goldens: list[GoldenCase],
    predictions: list[PredictedCase],
) -> dict[str, Any]:
    """跨合同聚合评测 (micro average), 并按 single / mixed 分组."""
    pred_by_id = {p.contract_id: p for p in predictions}
    empty = PredictedCase(contract_id="")
    rows = [
        match_case(g, pred_by_id.get(g.contract_id, empty))
        for g in goldens
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row)
    return {
        "cases": rows,
        "overall": _aggregate(rows),
        "by_group": {name: _aggregate(group) for name, group in sorted(groups.items())},
        "golden_count": len(goldens),
        "prediction_count": len(predictions),
        "unmatched_predictions": sorted(
            set(pred_by_id) - {g.contract_id for g in goldens}
        ),
        "disclaimer": (
            "本报告衡量合同级审查效果; 检索层 hit@k/MRR 不得作为审查准确率引用。"
        ),
    }


# ─── 与报告接口对接 ────────────────────────────────────────────


def predictions_from_report(report: dict[str, Any]) -> PredictedCase:
    """把 ``GET /contracts/{id}/report`` 的响应转换成评测输入."""
    return PredictedCase(
        contract_id=_value(report.get("contract_id", "")),
        risks=tuple(
            PredictedRisk(
                category=_value(r.get("category", "")),
                level=_value(r.get("level", "")),
                original_clause=str(r.get("original_clause", "") or ""),
            )
            for r in report.get("risk_items", [])
        ),
        missing_clauses=tuple(
            _value(m.get("key", "")) for m in report.get("missing_clauses", [])
        ),
    )


def load_goldens(path: Path) -> list[GoldenCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenCase(
            contract_id=str(row["contract_id"]),
            group=str(row.get("group", "single")),
            risks=tuple(
                GoldenRisk(
                    category=str(r["category"]),
                    level=str(r.get("level", "high")),
                    clause_snippet=str(r.get("clause_snippet", "")),
                    required=bool(r.get("required", True)),
                )
                for r in row.get("risks", [])
            ),
            missing_clauses=tuple(str(k) for k in row.get("missing_clauses", [])),
        )
        for row in payload
    ]


def load_predictions(path: Path) -> list[PredictedCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        predictions_from_report(row) if "risk_items" in row else PredictedCase(
            contract_id=str(row["contract_id"]),
            risks=tuple(
                PredictedRisk(
                    category=str(r["category"]),
                    level=str(r.get("level", "")),
                    original_clause=str(r.get("original_clause", "")),
                )
                for r in row.get("risks", [])
            ),
            missing_clauses=tuple(str(k) for k in row.get("missing_clauses", [])),
        )
        for row in payload
    ]


# ─── 发布门禁 ─────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent
DEFAULT_GATE_FILE = _ROOT / "gate_thresholds.json"

#: 未显式提供阈值文件时的保守默认值 (可被 gate_thresholds.json 覆盖)
DEFAULT_GATE: dict[str, Any] = {
    "min_precision": 0.6,
    "min_recall": 0.8,
    "min_f1": 0.7,
    "min_level_agreement": 0.6,
    "max_severe_misses": 0,
    "min_missing_precision": 0.6,
    "min_missing_recall": 0.8,
    "require_complete_predictions": True,
}


def load_thresholds(path: Path) -> dict[str, Any]:
    """读取阈值文件; 下划线开头的注释键不参与判定."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def check_gate(
    result: dict[str, Any], thresholds: dict[str, Any] | None = None
) -> dict[str, Any]:
    """按阈值判定是否允许发布, 返回逐项可审计的检查明细.

    严重漏报 (required+high 未检出) 是硬红线, 默认必须为 0。
    """
    limits = {**DEFAULT_GATE, **(thresholds or {})}
    overall = result["overall"]
    missing_metrics = overall.get("missing_metrics", {})
    actual = {
        "precision": overall.get("precision", 0.0),
        "recall": overall.get("recall", 0.0),
        "f1": overall.get("f1", 0.0),
        "level_agreement": overall.get("level_agreement", 0.0),
        "severe_misses": overall.get("severe_misses", 0),
        "missing_precision": missing_metrics.get("precision", 0.0),
        "missing_recall": missing_metrics.get("recall", 0.0),
        "predicted_cases": result.get("prediction_count", 0),
        "golden_cases": result.get("golden_count", 0),
    }
    specs = (
        ("precision", "min_precision", ">="),
        ("recall", "min_recall", ">="),
        ("f1", "min_f1", ">="),
        ("level_agreement", "min_level_agreement", ">="),
        ("severe_misses", "max_severe_misses", "<="),
        ("missing_precision", "min_missing_precision", ">="),
        ("missing_recall", "min_missing_recall", ">="),
    )
    checks: list[dict[str, Any]] = []
    for metric, key, op in specs:
        limit = limits[key]
        ok = actual[metric] >= limit if op == ">=" else actual[metric] <= limit
        checks.append(
            {"metric": metric, "actual": actual[metric], "limit": limit, "op": op, "ok": ok}
        )
    if limits.get("require_complete_predictions", True):
        expected = actual["golden_cases"]
        checks.append(
            {
                "metric": "predicted_cases",
                "actual": actual["predicted_cases"],
                "limit": expected,
                "op": "==",
                "ok": actual["predicted_cases"] == expected,
            }
        )
    violations = [c for c in checks if not c["ok"]]
    return {
        "passed": not violations,
        "thresholds": limits,
        "checks": checks,
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合同级端到端审查效果评测")
    parser.add_argument("--goldens", type=Path, default=_ROOT / "goldens" / "review_golden.json")
    parser.add_argument("--predictions", type=Path, default=_ROOT / "output" / "review_predictions.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--gate", action="store_true", help="启用发布门禁, 未通过时返回退出码 1")
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_GATE_FILE)
    args = parser.parse_args(argv)

    result = evaluate(load_goldens(args.goldens), load_predictions(args.predictions))
    if args.gate:
        result["gate"] = check_gate(result, load_thresholds(args.thresholds))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"评测结果已写入 {args.out}")
    print(json.dumps(result["overall"], ensure_ascii=False, indent=2))
    if args.gate:
        gate = result["gate"]
        print(
            json.dumps(
                {"gate_passed": gate["passed"], "violations": gate["violations"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if gate["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
