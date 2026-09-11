"""
混合检索融合: RRF 排序 + 通道路相关度分数.

排序: 将向量通道 (Milvus) 与 BM25 关键词通道的独立排序结果按
``Σ 1/(rrf_k + rank)`` 累计融合分, 缓解各通道分数不可比的问题。

相关度分数 (similarity, 0~1): RRF 融合分只含名次信息, 映射出的
分数无法反映「匹配得有多好」; 因此在首个包含命中项的通道条目上,
用两通道的真实分数加权计算——

- 双通道命中: ``w_vec · 余弦相似度 + w_bm25 · BM25归一``
  (BM25 无界分按通道内最高分缩放; 余弦相似度已是 0~1 直接使用);
- 单通道命中: 该通道归一化分数 × 折扣因子 (缺少另一通道佐证);
- 两通道均无有效分数时: 退化为位次置信度 ``1/(2 + 名次)``。
"""

from __future__ import annotations

__all__ = ["reciprocal_rank_fusion"]


def _clamp01(value: float) -> float:
    """截断到 [0, 1]."""
    return max(0.0, min(1.0, value))


def _normalized_channel_score(score: float, channel_max: float) -> float:
    """单条命中在通道内的归一化分数 (0~1).

    通道内分数均不超过 1 (如余弦相似度) 时按绝对值使用, 保留
    「匹配强度」语义; 否则 (如无界 BM25 分) 按通道内最高分缩放。
    """
    if channel_max > 1.0:
        return _clamp01(score / channel_max)
    return _clamp01(score)


def reciprocal_rank_fusion(
    channel_results: list[list[dict]],
    top_k: int = 5,
    rrf_k: int = 60,
    channel_weights: list[float] | None = None,
    single_channel_factor: float = 1.0,
) -> list[dict]:
    """
    RRF 融合多个通道的检索结果.

    Args:
        channel_results: 各通道命中列表, 命中为含 law_name/article 的 dict;
            列表中靠前的项代表更高名次。命中可携带 ``score`` 字段
            (通道原始分), 用于计算融合后的相关度分数。
        top_k: 融合后返回的最大条数。
        rrf_k: RRF 平滑参数 (默认 60, 标准取值)。
        channel_weights: 与 ``channel_results`` 按位置对齐的通道权重
            (缺省时各通道等权); 仅影响 similarity 的加权, 不影响排序。
        single_channel_factor: 仅单通道命中时的相似度折扣因子
            (0~1, 缺省 1.0 不打折)。

    Returns:
        融合后按分数降序的命中列表; 每条在首个包含它的通道条目基础上
        附加 fusion_rrf (排序分)、similarity (相关度分数, 0~1) 与
        channels 字段, 供调试与口径说明。
    """
    n_channels = len(channel_results)
    weights = [
        _clamp01(float(channel_weights[i]))
        if channel_weights and i < len(channel_weights)
        else 1.0
        for i in range(n_channels)
    ]

    # 各通道分数上界 (仅统计数值型正分); 无有效分数时该通道不参与相似度
    channel_max: list[float] = []
    for channel_hits in channel_results:
        positive = [
            float(h["score"])
            for h in channel_hits
            if isinstance(h.get("score"), (int, float)) and float(h["score"]) > 0
        ]
        channel_max.append(max(positive) if positive else 0.0)

    fused: dict[tuple[str, str], dict] = {}
    hit_scores: dict[tuple[str, str], dict[int, float]] = {}

    for i, channel_hits in enumerate(channel_results):
        for rank, hit in enumerate(channel_hits):
            key = (hit["law_name"], hit["article"])
            entry = fused.setdefault(
                key,
                {k: v for k, v in hit.items() if k not in {"_channel", "score"}},
            )
            entry["fusion_rrf"] = entry.get("fusion_rrf", 0.0) + 1.0 / (rrf_k + rank + 1)
            entry["channels"] = entry.get("channels", set())
            entry["channels"].add(hit.get("_channel", "unknown"))

            score = hit.get("score")
            if (
                isinstance(score, (int, float))
                and float(score) > 0
                and channel_max[i] > 0
            ):
                hit_scores.setdefault(key, {})[i] = float(score)

    ranked = sorted(
        fused.values(),
        key=lambda e: float(e["fusion_rrf"]),
        reverse=True,
    )[:top_k]

    for pos, entry in enumerate(ranked):
        key = (entry["law_name"], entry["article"])
        scores = hit_scores.get(key, {})
        if scores:
            weight_sum = sum(weights[i] for i in scores)
            if weight_sum <= 0:
                weight_sum = 1.0
            similarity = sum(
                weights[i] * _normalized_channel_score(s, channel_max[i])
                for i, s in scores.items()
            ) / weight_sum
            if len(scores) == 1:
                similarity *= single_channel_factor  # 缺少另一通道佐证
        else:
            # 无通道分数可用: 退化为位次置信度 (0~1, 位置越靠前越高)
            similarity = 1.0 / (2.0 + pos)
        entry["similarity"] = round(_clamp01(similarity), 4)
        entry["channels"] = sorted(entry["channels"])
    return ranked
