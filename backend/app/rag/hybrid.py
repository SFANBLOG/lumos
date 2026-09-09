"""
混合检索融合: Reciprocal Rank Fusion (RRF).

将向量通道 (Milvus) 与 BM25 关键词通道的独立排序结果融合,
对每条命中按 ``Σ 1/(rrf_k + rank)`` 累计融合分, 缓解各通道分数
量纲不可比的问题, 得到最终相关度排序。
"""

from __future__ import annotations

__all__ = ["reciprocal_rank_fusion"]


def reciprocal_rank_fusion(
    channel_results: list[list[dict]],
    top_k: int = 5,
    rrf_k: int = 60,
) -> list[dict]:
    """
    RRF 融合多个通道的检索结果.

    Args:
        channel_results: 各通道命中列表, 命中为含 law_name/article 的 dict;
            列表中靠前的项代表更高名次。
        top_k: 融合后返回的最大条数。
        rrf_k: RRF 平滑参数 (默认 60, 标准取值).

    Returns:
        融合后按分数降序的命中列表; 每条在首个包含它的通道条目基础上
        附加 fusion_rrf 与 channels 字段, 供调试与口径说明。
    """
    fused: dict[tuple[str, str], dict] = {}

    for channel_hits in channel_results:
        for rank, hit in enumerate(channel_hits):
            key = (hit["law_name"], hit["article"])
            entry = fused.setdefault(
                key,
                {k: v for k, v in hit.items() if k not in {"_channel", "score"}},
            )
            entry["fusion_rrf"] = entry.get("fusion_rrf", 0.0) + 1.0 / (rrf_k + rank + 1)
            entry["channels"] = entry.get("channels", set())
            entry["channels"].add(hit.get("_channel", "unknown"))

    ranked = sorted(
        fused.values(),
        key=lambda e: float(e["fusion_rrf"]),
        reverse=True,
    )[:top_k]

    for pos, entry in enumerate(ranked):
        # 排序置信度 (0~1, 位置越靠前越高), 供 relevance_score 等使用
        entry["similarity"] = round(1.0 / (2.0 + pos), 4)
        entry["channels"] = sorted(entry["channels"])
    return ranked
