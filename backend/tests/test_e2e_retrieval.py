"""
端到端检索评测 (e2e marker, 默认跳过).

与单元测试不同, 本文件跑「真实链路」: 本地 embedding 模型推理 +
Milvus 向量库 + BM25 + RRF 融合, 不再注入任何假对象,
用于验证生产检索链路可用并产出真实指标。

前置条件:
- 本地 embedding 模型可加载 (默认 paraphrase-multilingual-MiniLM-L12-v2,
  首次运行自动下载) 或已配置 EMBEDDING_PROVIDER=api;
- Milvus 不可用时向量通道关闭, 仅保留 BM25 关键词检索。

运行:
    LUMOS_E2E=1 python -m pytest tests/test_e2e_retrieval.py -m e2e -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("LUMOS_E2E") != "1",
        reason="端到端评测需显式开启: LUMOS_E2E=1 (真实 embedding + 向量库)",
    ),
]

_EVAL_MODULE = "eval.retrieval_eval"


@pytest.fixture(scope="module")
def small_goldens() -> list:
    """加载 9 类各 1 份金标准 (真实合同文本 + 自动查询)."""
    eval_mod = pytest.importorskip(_EVAL_MODULE)
    contracts_dir = Path(__file__).resolve().parents[2] / "data" / "contracts"
    goldens = eval_mod.load_goldens(contracts_dir, limit=9)
    assert len(goldens) == 9, "期望 9 类目录各取 1 条金标准"
    return goldens


def test_real_chain_search_returns_hits_with_channel_tags() -> None:
    """真实链路: 混合检索返回带 RRF/channels 的命中, 覆盖 9 类查询."""
    from app.rag.embeddings import EmbeddingNotReadyError
    from app.rag.law_corpus import ALL_LAWS
    from app.rag.vector_store import init_vector_store, search_laws

    try:
        init_vector_store()
    except EmbeddingNotReadyError as e:
        pytest.skip(f"embedding 通道不可用: {e}")

    queries = ["竞业限制 违约金 两年内", "试用期 社会保险 缴纳", "年休假 五天 累计工龄"]
    for q in queries:
        hits = search_laws(q, n_results=5)
        assert hits, f"真实链路检索为空: {q}"
        for hit in hits:
            assert "fusion_rrf" in hit and "channels" in hit and "similarity" in hit
    # 语料至少覆盖一个命中类别
    cats = {h.get("category") for h in search_laws(queries[0], n_results=5)}
    assert cats & {l["category"] for l in ALL_LAWS}


def test_e2e_eval_metrics_produced(small_goldens: list) -> None:
    """端到端指标可产出: 三通道均给出 hit@k 且值域合法."""
    eval_mod = pytest.importorskip(_EVAL_MODULE)
    from app.rag.embeddings import EmbeddingNotReadyError
    from app.rag.vector_store import init_vector_store

    try:
        init_vector_store()
    except EmbeddingNotReadyError as e:
        pytest.skip(f"embedding 通道不可用: {e}")

    for channel in ("vector", "bm25", "hybrid"):
        metrics = eval_mod.evaluate_channel(channel, small_goldens, top_k=5)
        assert metrics["n_queries"] == 9
        for key in ("hit@1", "hit@3", "hit@5", "mrr@5"):
            assert 0 <= metrics[key] <= 1, f"{channel} {key} 越界: {metrics[key]}"
