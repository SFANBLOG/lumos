"""生成合同级端到端评测的预测集.

两种数据源, 覆盖离线与联调两种发布场景:

1. ``--reports``: 直接把已保存的报告响应 JSON 列表转成预测集 (无需服务);
2. 默认联调: 读取 ``goldens/contracts.json``, 逐份提交到真实 API,
   轮询状态至完成后拉取报告, 并把 ``contract_id`` 映射回金标准 ID。

用法::

    python -m eval.generate_predictions --reports eval/output/reports.json
    python -m eval.generate_predictions --base-url http://127.0.0.1:8000/api/v1 \
        --token <JWT> --out eval/output/review_predictions.json
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from eval.review_eval import predictions_from_report

_ROOT = Path(__file__).resolve().parent
_DEFAULT_CASES = _ROOT / "goldens" / "contracts.json"
_DEFAULT_OUT = _ROOT / "output" / "review_predictions.json"
_DEFAULT_REPORTS_OUT = _ROOT / "output" / "reports.json"


def _http(
    method: str,
    url: str,
    payload: dict | None,
    headers: dict[str, str],
    timeout: float = 30.0,
) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _headers(token: str, api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def from_reports(reports: list[dict]) -> list[dict]:
    """报告响应列表 → ``load_predictions`` 可直接读取的预测集."""
    rows: list[dict] = []
    for report in reports:
        predicted = predictions_from_report(report)
        rows.append(
            {
                "contract_id": predicted.contract_id,
                "risks": [
                    {
                        "category": r.category,
                        "level": r.level,
                        "original_clause": r.original_clause,
                    }
                    for r in predicted.risks
                ],
                "missing_clauses": list(predicted.missing_clauses),
            }
        )
    return rows


def submit_and_collect(
    base_url: str,
    cases: list[dict],
    headers: dict[str, str],
    poll_interval: float = 2.0,
    max_wait: float = 300.0,
) -> list[dict]:
    """逐份提交真实合同, 等待分析完成并拉取报告 (用真实 API 跑端到端)."""
    reports: list[dict] = []
    for case in cases:
        contract_id = str(case["contract_id"])
        payload = {
            "text": str(case["raw_text"]),
            "source": "text_paste",
            "contract_type": str(case.get("contract_type", "auto")),
            "force": True,
        }
        submitted = _http("POST", f"{base_url}/contracts", payload, headers)
        real_id = submitted["contract_id"]
        deadline = time.monotonic() + max_wait
        while True:
            row = _http("GET", f"{base_url}/contracts/{real_id}", None, headers)
            status = str(row.get("status", ""))
            if status == "completed":
                break
            if status == "failed":
                raise RuntimeError(f"{contract_id}: 分析失败 ({real_id})")
            if time.monotonic() > deadline:
                raise TimeoutError(f"{contract_id}: 等待分析完成超时 ({real_id})")
            time.sleep(poll_interval)
        report = _http("GET", f"{base_url}/contracts/{real_id}/report", None, headers)
        report["contract_id"] = contract_id  # 对齐金标准 ID
        reports.append(report)
        print(f"  ✓ {contract_id} → {real_id[:8]} | 风险 {len(report.get('risk_items', []))} 条")
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成端到端审查评测预测集")
    parser.add_argument("--reports", type=Path, default=None, help="已有报告响应列表 JSON")
    parser.add_argument("--cases", type=Path, default=_DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    parser.add_argument("--reports-out", type=Path, default=_DEFAULT_REPORTS_OUT)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--token", default=os.getenv("LUMOS_API_TOKEN", ""))
    parser.add_argument("--api-key", default=os.getenv("LUMOS_API_KEY", ""))
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--max-wait", type=float, default=300.0)
    args = parser.parse_args(argv)

    if args.reports:
        reports = json.loads(args.reports.read_text(encoding="utf-8"))
    else:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        reports = submit_and_collect(
            args.base_url.rstrip("/"),
            cases,
            _headers(args.token, args.api_key),
            poll_interval=args.poll_interval,
            max_wait=args.max_wait,
        )
        args.reports_out.parent.mkdir(parents=True, exist_ok=True)
        args.reports_out.write_text(
            json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    predictions = from_reports(reports)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"预测集已写入 {args.out} | 合同 {len(predictions)} 份")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
