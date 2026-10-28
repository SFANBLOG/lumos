"""
检索链路离线评测: 金标准 hit@k 对比 (向量 / BM25 / 混合 RRF).

金标准来源 (``data/contracts``): 高危/警惕/关注 三区共 9 个风险类别目录,
每类 10 份单风险合同样本 (001-090)。对每份样本:
- 目录名 → 金标准风险类别;
- 从合同文本中自动抽取「风险句」作为查询 (命中类别触发词的第一个句子)。

对每个查询分别以三种通道检索法条库 (14 部法律法规完整条文):
- ``vector``: 仅向量通道 (Milvus, 真实 embedding);
- ``bm25``:  仅 BM25 关键词通道 (jieba 分词);
- ``hybrid``: 两通道 RRF 融合 (生产环境实际入口 search_laws)。

统计 hit@1 / hit@3 / hit@5 与 MRR@5 并输出对比。

口径说明:
- 本评测衡量「检索效果」, 属效果指标; 测试用例数 / 代码行数等
  属开发规模指标, 不用于衡量效果 (详见 docs/technical-design.md)。
- ``综合区`` (样本 091-100) 为多风险混合合同, 单标签金标准不成立,
  不纳入自动评测, 需人工标注后方可扩展。

用法 (backend 目录下):
    python -m eval.retrieval_eval [--topk 5] [--limit 0] [--out-dir eval/output]

首次运行会自动下载本地 embedding 模型 (或配置 EMBEDDING_PROVIDER=api)。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from loguru import logger

# ── 金标准映射与查询抽取 ──────────────────────────────────────

#: 单风险目录名 → 法条库风险类别 (与 app.rag.law_corpus 一致)
_CATEGORY_DIRS: dict[str, str] = {
    "竞业禁止": "non_compete",
    "试用期社保": "probation_insurance",
    "强制扣薪": "salary_deduction",
    "岗位职责": "job_description",
    "服从一切安排": "obedience_clause",
    "离职审批": "resignation",
    "休假权益": "leave_rights",
    "管辖地争议": "jurisdiction",
    "培训服务期": "training_bond",
}

#: 各类别的文本触发词 (用于从合同样本中定位风险句)
_TRIGGERS: dict[str, list[str]] = {
    "non_compete": ["竞业限制", "竞业禁止", "竞业", "保密", "同业", "离职后"],
    "probation_insurance": ["试用期", "社会保险", "社保", "缴纳", "保险"],
    "salary_deduction": ["克扣", "扣除", "扣发", "罚款", "工资", "赔偿"],
    "job_description": ["岗位", "工作内容", "职责", "职务", "调岗"],
    "obedience_clause": ["服从", "安排", "调动", "指派", "随时"],
    "resignation": ["离职", "辞职", "审批", "批准", "离职手续", "交接"],
    "leave_rights": ["休假", "年假", "婚假", "产假", "病假", "加班", "休息", "假日"],
    "jurisdiction": ["管辖", "仲裁", "法院", "诉讼", "争议解决"],
    "training_bond": ["培训", "服务期", "培训费", "深造", "学费", "违约金"],
}

_SENTENCE_SPLIT = re.compile(r"[。；;！？\n\r]+")


@dataclass
class Golden:
    """一条金标准: 合同样本 + 金标准风险类别 + 自动抽取的查询句."""

    contract_id: str
    category: str
    query: str
    file: str


def _read_text(path: Path) -> str:
    """读取合同样本 (UTF-8, 兼容 GBK)."""
    for encoding in ("utf-8", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_query(text: str, triggers: list[str]) -> str:
    """
    抽取风险句: 首个命中触发词的句子为起点.

    起点可能只是条款标题 (如「九、保密与竞业限制」), 因此顺延拼接
    后续句子补足上下文 (上限 4 句 / 60 字), 再截断到 160 字。
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.strip()) >= 4]
    start = next(
        (i for i, s in enumerate(sentences) if any(t in s for t in triggers)),
        -1,
    )
    if start < 0:
        return "".join(sentences[:2])[:160]  # 触发词缺失时取全文前两句兜底
    picked = [sentences[start]]
    j = start + 1
    while j < len(sentences) and len("".join(picked)) < 60 and j - start <= 4:
        picked.append(sentences[j])
        j += 1
    return "".join(picked)[:160]


def load_goldens(
    contracts_dir: Path,
    limit: int = 0,
) -> list[Golden]:
    """加载金标准: 遍历 高危/警惕/关注 三区下的类别目录 (跳过 综合区)."""
    goldens: list[Golden] = []
    for level in ("高危区", "警惕区", "关注区"):
        level_dir = contracts_dir / level
        if not level_dir.is_dir():
            continue
        for category_dir in sorted(p for p in level_dir.iterdir() if p.is_dir()):
            category = _CATEGORY_DIRS.get(category_dir.name)
            if category is None:
                logger.warning(f"跳过未映射的类别目录: {category_dir.name}")
                continue
            triggers = _TRIGGERS[category]
            for file in sorted(category_dir.glob("*.txt")):
                query = _extract_query(_read_text(file), triggers)
                goldens.append(
                    Golden(
                        contract_id=file.stem,
                        category=category,
                        query=query,
                        file=str(file.relative_to(contracts_dir)),
                    )
                )
                if limit and len(goldens) >= limit:
                    return goldens
    return goldens


# ── 三通道检索 ────────────────────────────────────────────────


def _channel_categories(hits: list[dict]) -> list[str]:
    """按序取命中条文的 category 序列 (命中可能重复, 原样保留)."""
    return [h.get("category", "") for h in hits]


def run_retrieval(
    query: str,
    top_k: int,
    channel: str,
) -> list[dict]:
    """按通道检索法条库 (向量 / bm25 / hybrid 均与生产同一实现)."""
    if channel == "vector":
        from app.rag import vector_store

        return vector_store._vector_search(query, n_results=top_k, category=None)
    if channel == "bm25":
        from app.rag.bm25_index import bm25_search_laws

        return bm25_search_laws(query, top_k=top_k, category=None)
    if channel == "hybrid":
        from app.rag.vector_store import search_laws

        return search_laws(query, n_results=top_k, category=None)
    raise ValueError(f"未知检索通道: {channel}")


def evaluate_channel(
    channel: str,
    goldens: list[Golden],
    top_k: int = 5,
) -> dict:
    """跑完单个通道的全部金标准查询, 返回 hit@k / MRR 指标."""
    hit = {k: 0 for k in (1, 3, 5) if k <= top_k}
    rr_sum = 0.0
    failed = 0
    n = len(goldens)

    for golden in goldens:
        try:
            cats = _channel_categories(run_retrieval(golden.query, top_k, channel))
        except Exception as e:  # noqa: BLE001 - 单条失败不应中断整轮评测
            logger.error(f"[{channel}] 查询失败 {golden.contract_id}: {e}")
            failed += 1
            continue
        for k in hit:
            if golden.category in cats[:k]:
                hit[k] += 1
        for rank, cat in enumerate(cats, start=1):
            if cat == golden.category:
                rr_sum += 1.0 / rank
                break

    return {
        "channel": channel,
        "n_queries": n,
        "n_failed": failed,
        "hit@1": round(hit.get(1, 0) / n, 4),
        "hit@3": round(hit.get(3, 0) / n, 4),
        "hit@5": round(hit.get(5, 0) / n, 4),
        "mrr@5": round(rr_sum / n, 4),
        "total_clauses": None,  # 由调用方填充
    }


# ── 报告输出 ──────────────────────────────────────────────────


def _display_signature(sig: str) -> str:
    """报告展示用签名: 模型名为本地目录路径时取其目录名, 避免绝对路径入库."""
    provider, _, name = sig.partition(":")
    if any(ch in name for ch in ("\\", "/")):
        return f"{provider}:{Path(name).name}"
    return sig


def _markdown_report(results: list[dict], meta: dict) -> str:
    lines = [
        "# 检索链路离线评测报告 (金标准 hit@k 对比)",
        "",
        f"- 评测时间: {meta['timestamp']}",
        f"- embedding: `{_display_signature(meta['embedding_signature'])}`",
        f"- 金标准样本数: {meta['n_goldens']} (data/contracts 单风险区 9 类 × 10)",
        f"- 法条语料: {meta['n_law_docs']} 部法律 / {meta['n_laws']} 条核心条文",
        f"- 综合区样本 (多风险混合) 未纳入自动评测",
        "",
        "## 指标口径",
        "",
        "- **hit@k**: 前 k 条命中中出现金标准风险类别的样本占比;",
        "- **MRR@5**: 首个正确条文排名的倒数均值;",
        "- 三通道共享同一组查询与金标准, 差异仅来自检索方式,",
        "  直接可比 (hybrid 为生产入口: 向量 + BM25 + RRF)。",
        "",
        "## 结果对比",
        "",
        "| 通道 | hit@1 | hit@3 | hit@5 | MRR@5 | 失败查询 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r['channel']} | {r['hit@1']:.4f} | {r['hit@3']:.4f} | "
            f"{r['hit@5']:.4f} | {r['mrr@5']:.4f} | {r['n_failed']} |"
        )
    lines += [
        "",
        "## 检索效果与开发规模的边界",
        "",
        "- 本报告指标衡量的是「检索效果」(功能效果指标);",
        "- 测试用例数、代码行数、语料条数等均为「开发规模指标」,",
        "  不代表检索或审查效果, 两者不应混用。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="检索链路金标准评测 (hit@k 对比)")
    parser.add_argument("--topk", type=int, default=5, help="检索截断条数 (默认 5)")
    parser.add_argument("--limit", type=int, default=0, help="仅评测前 N 条金标准 (0=全部)")
    parser.add_argument("--out-dir", type=str, default="eval/output", help="报告输出目录")
    args = parser.parse_args()
    if args.topk < 5:
        raise SystemExit("--topk 至少为 5 (评测需要 hit@5)")

    contracts_dir = Path(__file__).resolve().parents[2] / "data" / "contracts"
    goldens = load_goldens(contracts_dir, limit=args.limit)
    if not goldens:
        raise SystemExit(f"未找到金标准样本: {contracts_dir}")
    logger.info(
        f"📋 金标准就绪 | {len(goldens)} 条 | 类别: "
        f"{sorted({g.category for g in goldens})}"
    )

    # 启动链路 (真实 embedding 加载 + 向量库初始化, 供 vector/hybrid 通道)
    from app.rag.embeddings import embedding_signature
    from app.rag.law_corpus import ALL_LAWS
    from app.rag.vector_store import init_vector_store

    init_vector_store()

    logger.info(f"🚀 开始评测 {len(goldens)} 条金标准 × 3 通道…")
    t0 = time.time()
    results = [
        evaluate_channel(ch, goldens, top_k=args.topk)
        for ch in ("vector", "bm25", "hybrid")
    ]
    elapsed = round(time.time() - t0, 1)

    meta = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "embedding_signature": embedding_signature(),
        "n_goldens": len(goldens),
        "n_laws": len(ALL_LAWS),
        "n_law_docs": len({law["law_name"] for law in ALL_LAWS}),
        "topk": args.topk,
        "elapsed_seconds": elapsed,
    }
    payload = {"meta": meta, "results": results}

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "retrieval_eval_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "retrieval_eval_latest.md").write_text(
        _markdown_report(results, meta), encoding="utf-8"
    )
    (out_dir / "gold_queries.json").write_text(
        json.dumps([asdict(g) for g in goldens], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(_markdown_report(results, meta))
    logger.info(
        f"✅ 评测完成 | {len(goldens)} 条 × 3 通道 | {elapsed}s | "
        f"报告: {out_dir / 'retrieval_eval_latest.md'}"
    )


if __name__ == "__main__":
    main()
