"""
检索链路单元测试.

覆盖: BM25 中文全文检索 / RRF 融合排序 / search_laws 混合检索入口
(通道降级与分类过滤) / embedding 通道抽象。
均不依赖外部服务与真实模型 (monkeypatch 注入)。
"""

from __future__ import annotations

from app.rag import vector_store
from app.rag.bm25_index import BM25Index, bm25_search_laws, zh_tokenize
from app.rag.embeddings import ApiEmbedder, EmbeddingNotReadyError, LocalSentenceTransformerEmbedder
from app.rag.hybrid import reciprocal_rank_fusion
from app.rag.law_corpus import ALL_LAWS


class _FakeVec(list):
    """模拟 numpy 向量 (提供 tolist)."""

    def tolist(self) -> list:
        return list(self)


class _FakeEncoded:
    """模拟 sentence-transformers 返回的 numpy 2-D 数组 (提供 tolist)."""

    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return [list(r) for r in self._rows]


# ─── BM25 中文检索 ──────────────────────────────────────────────


class TestBM25:
    def test_tokenize_keeps_chinese_terms(self) -> None:
        tokens = zh_tokenize("劳动者违反竞业限制约定的，应当支付违约金")
        assert "竞业限制" in tokens
        assert "违约金" in tokens
        assert all(t.strip() for t in tokens)

    def test_hits_competition_clause_on_keywords(self) -> None:
        """竞业限制关键词应命中 non_compete 类条文 (top2 内)."""
        hits = bm25_search_laws("竞业限制 两年内 同业", top_k=3)
        assert len(hits) == 3
        assert all(h["category"] == "non_compete" for h in hits[:2])
        assert hits[0]["law_name"] == "劳动合同法"

    def test_leave_rights_hits_annual_leave(self) -> None:
        hits = bm25_search_laws("年休假 累计工作满一年 年休假五天", top_k=2)
        assert hits[0]["law_name"] == "职工带薪年休假条例"

    def test_category_filter(self) -> None:
        hits = bm25_search_laws("工资 赔偿 加班", top_k=10, category="probation_salary")
        assert hits
        assert all(h["category"] == "probation_salary" for h in hits)

    def test_index_covers_full_corpus(self) -> None:
        index = BM25Index(ALL_LAWS)
        assert len(index.search("任意查询文本", top_k=len(ALL_LAWS))) == len(ALL_LAWS)


# ─── RRF 融合 ───────────────────────────────────────────────────


class TestRRF:
    def _hit(self, law_name: str, article: str, channel: str | None = None) -> dict:
        hit: dict = {"law_name": law_name, "article": article, "content": article}
        if channel:
            hit["_channel"] = channel
        return hit

    def test_merge_ranks_by_reciprocal(self) -> None:
        # 与真实链路一致: 融合前各通道命中已由 search_laws 打 _channel 标记
        vector = [self._hit("劳动合同法", "第二十三条", "vector"), self._hit("劳动合同法", "第二十四条", "vector")]
        bm25 = [self._hit("劳动合同法", "第二十四条", "bm25"), self._hit("劳动法", "第五十条", "bm25")]
        fused = reciprocal_rank_fusion([vector, bm25], top_k=3, rrf_k=60)
        # 双通道命中的「第二十四条」应排在单通道「第二十三条」之前
        assert fused[0]["article"] == "第二十四条"
        assert fused[0]["channels"] == ["bm25", "vector"]
        assert fused[0]["fusion_rrf"] > fused[1]["fusion_rrf"]

    def test_similarity_is_ranked_confidence(self) -> None:
        vector = [self._hit("劳动合同法", "第二十三条", "vector")]
        fused = reciprocal_rank_fusion([vector], top_k=1)
        assert 0 < fused[0]["similarity"] <= 1

    def test_top_k_trimming(self) -> None:
        vector = [self._hit(f"法律{i}", f"第{i}条") for i in range(5)]
        fused = reciprocal_rank_fusion([vector], top_k=3)
        assert len(fused) == 3


# ─── search_laws 混合检索入口 ───────────────────────────────────


class TestHybridSearch:
    def _law_hit(self, article: str, category: str = "non_compete") -> dict:
        return {
            "law_name": "劳动合同法",
            "article": article,
            "content": f"《劳动合同法》{article}内容",
            "keywords": "竞业限制",
            "category": category,
            "score": 0.9,
        }

    def test_fuses_vector_and_bm25(self, monkeypatch) -> None:
        def fake_vector(query: str, n_results: int, category: str | None) -> list[dict]:
            return [self._law_hit("第二十三条"), self._law_hit("第二十四条")]

        monkeypatch.setattr(vector_store, "_vector_search", fake_vector)
        hits = vector_store.search_laws("竞业限制 违约金", n_results=3)
        assert hits
        for hit in hits:
            assert 0 <= hit["similarity"] <= 1
            assert "fusion_rrf" in hit
            assert "channels" in hit

    def test_keeps_bm25_when_embedding_unavailable(self, monkeypatch) -> None:
        def broken_vector(query: str, n_results: int, category: str | None) -> list[dict]:
            raise EmbeddingNotReadyError("no embedding")

        monkeypatch.setattr(vector_store, "_vector_search", broken_vector)
        hits = vector_store.search_laws("试用期工资不得低于80%", n_results=3)
        assert hits
        assert all(h["channels"] == ["bm25"] for h in hits)

    def test_returns_empty_when_all_channels_fail(self, monkeypatch) -> None:
        def broken_vector(query: str, n_results: int, category: str | None) -> list[dict]:
            raise RuntimeError("vector down")

        monkeypatch.setattr(vector_store, "_vector_search", broken_vector)
        monkeypatch.setattr(vector_store, "bm25_search_laws", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bm25 down")))
        assert vector_store.search_laws("查询", n_results=3) == []

    def test_milvus_failure_disables_vector_channel(self, monkeypatch) -> None:
        import app.rag.milvus_store as milvus_store

        def broken_milvus(*args, **kwargs) -> list[dict]:
            raise RuntimeError("milvus unreachable")

        monkeypatch.setattr(milvus_store, "search_milvus", broken_milvus)
        hits = vector_store._vector_search("试用期", n_results=3, category=None)
        # 向量通道关闭, 不再回退 Chroma (sqlite); 返回空, BM25 关键词通道仍可用
        assert hits == []


# ─── Embedding 通道抽象 ─────────────────────────────────────────


class TestEmbedders:
    def test_local_embedder_signature_and_dim(self, monkeypatch) -> None:
        class FakeSentenceTransformer:
            def __init__(self, model_name: str) -> None:
                self.model_name = model_name

            def encode(self, texts: list[str], **kwargs) -> _FakeEncoded:
                return _FakeEncoded([_FakeVec([1.0, 0.0, 0.0]) for _ in texts])

        monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeSentenceTransformer)
        embedder = LocalSentenceTransformerEmbedder("fake-model")
        assert embedder.signature == "local:fake-model"
        assert embedder.dim == 3
        vectors = embedder.embed_texts(["甲", "乙"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 3

    def test_api_embedder_mocked(self, monkeypatch) -> None:
        class FakeOpenAIEmbeddings:
            def __init__(self, **kwargs: object) -> None:
                pass

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                return [[0.0, 1.0, 0.0]] * len(texts)

        monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeOpenAIEmbeddings)
        embedder = ApiEmbedder("bge-m3", "sk-test", "https://api.example.com/v1")
        assert embedder.signature == "api:bge-m3"
        vectors = embedder.embed_texts(["测试"])
        assert vectors == [[0.0, 1.0, 0.0]]

    def test_embedding_not_ready_message(self) -> None:
        err = EmbeddingNotReadyError("本地 embedding 依赖未安装")
        assert "本地 embedding" in str(err)
