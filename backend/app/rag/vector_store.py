"""
向量库管理 + 混合检索入口.

检索链路 (search_laws) — 双路召回 + RRF 融合 + 精排:
    1. 双路召回: 向量通道 Milvus (真实 embedding, COSINE)
       + 关键词通道 BM25 全文检索 (jieba 分词, 内存索引);
    2. RRF 融合: 两通道结果经 Reciprocal Rank Fusion (RRF) 融合排序,
       相关度分数 (similarity) 由两通道真实分数加权得出
       (向量权重见 hybrid_vector_weight 配置), 单通道命中打折;
    3. 精排: 融合候选经 rerank_candidates 重排 (轻量可解释精排 /
       可选 CrossEncoder 语义重排), 并按 retrieval_min_similarity 阈值过滤。

向量通道唯一后端为 Milvus (非 sqlite, 无 ChromaDB 降级路径);
Milvus 不可用时向量通道直接关闭, 仅保留 BM25 关键词检索, 应用仍可启动。
所有向量均由 ``app.rag.embeddings`` 的真实模型产出。
"""

from __future__ import annotations

from loguru import logger

from app.core.config import get_settings
from app.rag.bm25_index import bm25_search_laws
from app.rag.embeddings import (
    EmbeddingNotReadyError,
    embedding_dim,
    embedding_signature,
    embed_query,
    embed_texts,
)
from app.rag.hybrid import reciprocal_rank_fusion
from app.rag.reranker import rerank_candidates
from app.rag.law_corpus import ALL_LAWS, corpus_hash

settings = get_settings()


def _tag_channel(hit: dict, channel: str) -> dict:
    """为通道命中打标记 (供 RRF 融合统计)."""
    hit["_channel"] = channel
    return hit


# ── 向量通道 (仅 Milvus) ───────────────────────────────────────


def _vector_search(
    query: str,
    n_results: int,
    category: str | None,
) -> list[dict]:
    """向量通道: 仅 Milvus. 任意异常均关闭向量通道 (BM25 仍可用)."""
    try:
        from app.rag.milvus_store import search_milvus

        hits = search_milvus(query, n_results=n_results, category=category)
        logger.debug(f"[vector] Milvus 召回 {len(hits)} 条")
        return [_tag_channel(h, "vector") for h in hits]
    except EmbeddingNotReadyError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Milvus 检索失败, 跳过向量通道: {e}")
        return []


# ── 混合检索入口 ───────────────────────────────────────────────


def search_laws(
    query: str,
    n_results: int = 5,
    category: str | None = None,
) -> list[dict]:
    """混合检索: 双路召回 (向量 Milvus + BM25) → RRF 融合 → 精排 (Reranker).

    候选池按 top_k × max(hybrid_top_k_ratio, reranker_candidate_multiplier)
    放大, 先经 RRF 融合再交由 rerank_candidates 精排取前 n_results。
    任一通道不可用时自动降级 (仅剩单通道也能工作); 两通道全部
    不可用时返回空列表并记录错误, 不抛出异常。
    """
    pool = max(
        1,
        n_results * max(1, settings.hybrid_top_k_ratio, settings.reranker_candidate_multiplier),
    )

    vector_hits: list[dict] = []
    try:
        vector_hits = _vector_search(query, pool, category)
    except EmbeddingNotReadyError as e:
        logger.warning(f"⚠️ embedding 通道不可用, 仅 BM25 关键词通道: {e}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"向量通道检索失败: {e}")

    bm25_hits: list[dict] = []
    try:
        bm25_hits = [_tag_channel(h, "bm25") for h in bm25_search_laws(query, pool, category)]
    except Exception as e:  # noqa: BLE001
        logger.error(f"BM25 通道检索失败: {e}")

    if not vector_hits and not bm25_hits:
        logger.error("🚫 检索链路不可用: 向量通道与 BM25 通道均失败")
        return []

    # 相关度分数加权: 向量权重来自配置, BM25 权重取其补数
    vector_weight = min(1.0, max(0.0, settings.hybrid_vector_weight))
    fused = reciprocal_rank_fusion(
        [vector_hits, bm25_hits],
        top_k=pool,
        rrf_k=settings.rrf_k,
        channel_weights=[vector_weight, 1.0 - vector_weight],
        single_channel_factor=min(1.0, max(0.0, settings.hybrid_single_channel_factor)),
    )
    ranked = rerank_candidates(query, fused, top_k=n_results)
    logger.debug(
        f"[hybrid] 融合完成 | 候选: vector={len(vector_hits)} "
        f"bm25={len(bm25_hits)} → RRF={len(fused)} → 精排={len(ranked)} 条"
    )
    return ranked


# ── 初始化 ─────────────────────────────────────────────────────


def init_vector_store() -> None:
    """初始化向量库 (应用启动时调用), 仅 Milvus."""
    try:
        # 尽早暴露 embedding 配置问题 (真实模型加载/连通性)
        from app.rag.embeddings import get_embedder

        embedder = get_embedder()
        logger.info(f"🧠 embedding 就绪 | {embedder.signature} | dim={embedding_dim()}")
    except EmbeddingNotReadyError as e:
        logger.error(f"❌ embedding 通道不可用, 语义检索将不可用: {e}")
        return

    try:
        from app.rag.milvus_store import init_milvus

        init_milvus()
        logger.info("⚖️ Milvus 法律向量库就绪 (向量通道已启用)")
    except EmbeddingNotReadyError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ Milvus 不可用, 向量通道关闭, 仅保留 BM25 关键词检索: {e}")


# 供外部确认语料/embedding 签名 (调试用)
def vector_store_signature() -> str:
    """当前向量库签名 (embedding 通道 + 模型)."""
    return f"{embedding_signature()} | corpus={corpus_hash()[:8]} | laws={len(ALL_LAWS)}"
