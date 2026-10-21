"""
Embedding 通道降级测试: 首选 provider 不可用 (本地依赖缺失 / API Key 缺失) 时,
自动降级到另一可用通道兜底。

不加载真实模型 / 不联网: 仅验证 ``get_embedder`` 的通道选择降级逻辑。
"""

from __future__ import annotations

import pytest

from app.rag import embeddings
from app.rag.embeddings import EmbeddingNotReadyError, get_embedder


@pytest.fixture(autouse=True)
def _clear_cache():
    get_embedder.cache_clear()
    yield
    get_embedder.cache_clear()


def test_api_falls_back_to_local_when_key_missing(monkeypatch) -> None:
    settings = embeddings.get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "api")
    monkeypatch.setattr(settings, "embedding_api_key", "")
    emb = get_embedder()
    assert emb.provider == "local"


def test_local_falls_back_to_api_when_dep_missing(monkeypatch) -> None:
    settings = embeddings.get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "local")
    monkeypatch.setattr(settings, "embedding_api_key", "fake-key")
    monkeypatch.setattr(embeddings, "_local_available", lambda: False)
    emb = get_embedder()
    assert emb.provider == "api"


def test_both_unavailable_raises(monkeypatch) -> None:
    settings = embeddings.get_settings()
    monkeypatch.setattr(settings, "embedding_provider", "local")
    monkeypatch.setattr(settings, "embedding_api_key", "")
    monkeypatch.setattr(embeddings, "_local_available", lambda: False)
    with pytest.raises(EmbeddingNotReadyError):
        get_embedder()
