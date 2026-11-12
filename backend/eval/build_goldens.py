"""由人工标注合同生成端到端评测金标准.

``goldens/contracts.json`` 中每份合同由人标注「应有的风险」；缺失条款的
标准答案由确定性规则层 (``contract_facts`` / ``fact_semantics``) 现场计算，
避免手写金标准与规则实现漂移，也避免把检索命中率冒充审查准确率。

用法::

    python -m eval.build_goldens
    python -m eval.build_goldens --out eval/goldens/review_golden.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.agent.contract_facts import detect_missing_clauses, extract_contract_facts
from app.agent.fact_semantics import rules_for

_ROOT = Path(__file__).resolve().parent
_DEFAULT_CASES = _ROOT / "goldens" / "contracts.json"
_DEFAULT_OUT = _ROOT / "goldens" / "review_golden.json"


def build_goldens(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把人工风险标注 + 规则层缺口标注合成 GoldenCase 列表."""
    goldens: list[dict[str, Any]] = []
    for case in cases:
        contract_type = str(case.get("contract_type") or "labor_contract")
        rules = rules_for(contract_type)
        facts = extract_contract_facts(
            str(case.get("raw_text", "")),
            contract_type=contract_type,
            rules=rules,
        )
        missing = [m.key for m in detect_missing_clauses(facts, rules=rules)]
        goldens.append(
            {
                "contract_id": str(case["contract_id"]),
                "group": str(case.get("group", "single")),
                "contract_type": contract_type,
                "risks": list(case.get("risks", [])),
                "missing_clauses": missing,
            }
        )
    return goldens


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成合同级端到端评测金标准")
    parser.add_argument("--cases", type=Path, default=_DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = parser.parse_args(argv)

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    goldens = build_goldens(cases)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(goldens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"金标准已写入 {args.out} | 合同 {len(goldens)} 份 | "
        f"风险标注 {sum(len(g['risks']) for g in goldens)} 条 | "
        f"缺失条款标注 {sum(len(g['missing_clauses']) for g in goldens)} 条"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
