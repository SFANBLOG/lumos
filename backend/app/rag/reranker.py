"""检索候选重排：轻量可解释精排 + 可选 CrossEncoder 语义重排。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.rag.bm25_index import zh_tokenize


def _candidate_text(hit: dict[str, Any]) -> str:
    return " ".join(str(hit.get(key, "")) for key in ("law_name", "article", "content", "keywords"))


def _explainable_score(query: str, hit: dict[str, Any]) -> float:
    """不依赖额外模型的精排分，保留 score 构成以便审计。"""
    tokens = {token for token in zh_tokenize(query) if len(token) > 1}
    candidate = _candidate_text(hit)
    coverage = sum(token in candidate for token in tokens) / max(1, len(tokens))
    title_boost = sum(token in f"{hit.get('law_name', '')} {hit.get('article', '')}" for token in tokens) / max(1, len(tokens))
    retrieval = float(hit.get("similarity", 0.0))
    return min(1.0, 0.58 * retrieval + 0.30 * coverage + 0.12 * title_boost)


@lru_cache(maxsize=1)
def _cross_encoder():
    settings = get_settings()
    from sentence_transformers import CrossEncoder
    return CrossEncoder(settings.reranker_model_name, max_length=settings.reranker_max_length)


def rerank_candidates(query: str, candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """精排候选；CrossEncoder 故障时透明回退至可解释精排。"""
    if not candidates:
        return []
    settings = get_settings()
    scored = [dict(hit) for hit in candidates]
    method = "explainable"
    if settings.reranker_enabled:
        try:
            raw_scores = _cross_encoder().predict([(query, _candidate_text(hit)) for hit in scored])
            # sigmoid 归一，避免不同模型的 logit 量纲泄露到业务阈值。
            import math
            for hit, raw in zip(scored, raw_scores):
                hit["rerank_score"] = round(1 / (1 + math.exp(-float(raw))), 4)
            method = "cross_encoder"
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"CrossEncoder 重排不可用，回退可解释精排: {exc}")
    if method == "explainable":
        for hit in scored:
            hit["rerank_score"] = round(_explainable_score(query, hit), 4)

    for hit in scored:
        hit["rerank_method"] = method
        # 精排为主、RRF 相似度为辅，稳定保留多通道召回的价值。
        hit["final_score"] = round(0.75 * float(hit["rerank_score"]) + 0.25 * float(hit.get("similarity", 0)), 4)
    ranked = sorted(scored, key=lambda item: float(item["final_score"]), reverse=True)
    return [hit for hit in ranked[:top_k] if float(hit["final_score"]) >= settings.retrieval_min_similarity]
