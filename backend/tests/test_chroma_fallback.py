"""
Chroma 降级备库测试: 验证 Chroma 本地索引构建/检索, 以及 Milvus 故障时向量通道
降级到 Chroma (仍为语义向量检索, 而非退化为仅 BM25).

不依赖外部 Milvus 服务: 通过 mock embedding 构建本地 Chroma 索引, 并强制 Milvus
检索抛异常以触发降级路径。
"""

from __future__ import annotations

import pytest

from app.rag import chroma_store
from app.rag.vector_store import _vector_search


@pytest.fixture
def fake_embedding(monkeypatch, tmp_path):
    """用确定性低维向量替换真实 embedding, 并把 Chroma 持久化重定向到临时目录."""
    dim = 8

    def _texts(texts: list[str]) -> list[list[float]]:
        return [[float((idx * 3 + j) % 7) / 7 for j in range(dim)] for idx in range(len(texts))]

    def _query(text: str) -> list[float]:
        h = abs(hash(text)) % 7
        return [float((h + j) % 7) / 7 for j in range(dim)]

    monkeypatch.setattr(chroma_store, "embed_texts", _texts)
    monkeypatch.setattr(chroma_store, "embed_query", _query)
    monkeypatch.setattr(chroma_store, "embedding_dim", lambda: dim)

    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "chroma_persist_dir", str(tmp_path / "chroma"))

    chroma_store.get_chroma_client.cache_clear()
    chroma_store.get_chroma_collection.cache_clear()
    yield
    chroma_store.get_chroma_client.cache_clear()
    chroma_store.get_chroma_collection.cache_clear()


def test_chroma_build_and_search(fake_embedding) -> None:
    chroma_store.init_chroma()
    hits = chroma_store.search_chroma("竞业限制经济补偿", n_results=3)
    assert isinstance(hits, list)
    assert 0 < len(hits) <= 3
    for h in hits:
        assert {"law_name", "article", "content", "category", "score"} <= set(h)
        assert 0.0 <= h["score"] <= 1.0


def test_vector_search_falls_back_to_chroma(fake_embedding, monkeypatch) -> None:
    chroma_store.init_chroma()

    def _boom(*_a, **_k):
        raise RuntimeError("Milvus down")

    # 强制 Milvus 检索失败 → 触发 Chroma 降级 (from import 会读取被 mock 的函数)
    monkeypatch.setattr("app.rag.milvus_store.search_milvus", _boom)

    hits = _vector_search("竞业限制", 3, None)
    assert len(hits) > 0
    # 降级后仍为向量通道 (而非 BM25), 通道标记保持一致
    assert all(h.get("_channel") == "vector" for h in hits)
