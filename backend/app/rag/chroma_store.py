"""
Chroma 本地向量库封装 (Milvus 的降级备库).

当 Milvus 不可用 (服务宕机/未部署) 时, 由嵌入式 Chroma (PersistentClient,
本地 sqlite + hnswlib) 兜住向量通道, 保证语义检索在纯 Milvus 故障时仍可工作,
而非退化为仅 BM25 关键词检索。

- 向量由同一 embedding 模型产出, 与 Milvus 同构 (同一签名隔离策略);
- 集合名 = 基名 + embedding 签名后缀, 与 Milvus 的 ``collection_full_name`` 一致;
- 持久化路径由 settings.chroma_persist_dir 控制 (默认 backend/data/chroma),
  缺配置时自动回退默认值, 不强制依赖 config 字段。
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from loguru import logger

from app.core.config import get_settings
from app.rag.embeddings import embedding_dim, embedding_signature, embed_query, embed_texts
from app.rag.law_corpus import ALL_LAWS


def _chroma_collection_name() -> str:
    """实际集合名: 基名 + embedding 签名哈希 (8 位)."""
    sig_hash = hashlib.sha256(embedding_signature().encode("utf-8")).hexdigest()[:8]
    base = getattr(get_settings(), "chroma_collection", "lumos_laws")
    return f"{base}_{sig_hash}"


def _resolve_persist_dir() -> str:
    """解析 Chroma 持久化目录 (相对路径基于 backend 根, 自动创建)."""
    raw = getattr(get_settings(), "chroma_persist_dir", "data/chroma")
    p = Path(raw)
    if not p.is_absolute():
        backend_root = Path(__file__).resolve().parents[2]
        p = backend_root / p
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


@lru_cache
def get_chroma_client():
    """获取 (缓存) Chroma 持久化客户端."""
    import chromadb

    return chromadb.PersistentClient(path=_resolve_persist_dir())


@lru_cache
def get_chroma_collection():
    """获取 (缓存) Chroma 集合 (余弦距离空间, 与 Milvus COSINE 对齐)."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=_chroma_collection_name(),
        metadata={"hnsw:space": "cosine"},
    )


def _drifted(collection) -> bool:
    """语料漂移检测: 条数不一致或首条名称不一致时重建."""
    try:
        if collection.count() != len(ALL_LAWS):
            return True
        res = collection.get(limit=1, include=["metadatas"])
        if not res.get("ids"):
            return True
        meta = res["metadatas"][0]
        return meta.get("law_name") != ALL_LAWS[0]["law_name"]
    except Exception:  # noqa: BLE001
        return True


def init_chroma() -> None:
    """将法条语料向量化写入本地 Chroma (幂等). 作为 Milvus 的降级备库."""
    try:
        collection = get_chroma_collection()
        name = _chroma_collection_name()
        if collection.count() > 0:
            if _drifted(collection):
                logger.info(f"🔄 Chroma 语料/embedding 变化, 重建: {name}")
                get_chroma_client().delete_collection(name)
                collection = get_chroma_collection()
            else:
                logger.info(f"✅ Chroma 已就绪 | {name} | {collection.count()} 条")
                return

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        texts: list[str] = []
        for i, law in enumerate(ALL_LAWS):
            kw = ", ".join(law.get("keywords", []))
            # 向量化文本 = 法条全文 (名称/编号/正文/关键词), 与 Milvus 同构
            texts.append(f"{law['law_name']} {law['article']} {law['content']} {kw}")
            ids.append(str(i))
            metas.append({
                "law_name": law["law_name"],
                "article": law["article"],
                "category": law.get("category", ""),
                "keywords": kw,
            })
            docs.append(law["content"])

        logger.info(f"🧠 Chroma 向量化 {len(texts)} 条法条 (模型: {embedding_signature()})…")
        vectors = embed_texts(texts)
        collection.add(ids=ids, embeddings=vectors, documents=docs, metadatas=metas)
        logger.info(
            f"✅ Chroma 加载完成 | {name} | {len(ids)} 条 | dim={len(vectors[0])}"
        )
    except Exception as e:
        logger.error(f"❌ Chroma 初始化失败: {e}")
        raise


def search_chroma(
    query: str,
    n_results: int = 5,
    category: str | None = None,
) -> list[dict]:
    """向量通道降级语义检索 (余弦相似度降序, 与 search_milvus 返回同构)."""
    collection = get_chroma_collection()
    total = collection.count() or 0
    if total == 0:
        return []
    qv = embed_query(query)
    where = {"category": category} if category else None
    res = collection.query(
        query_embeddings=[qv],
        n_results=min(n_results, total),
        where=where,
        include=["metadatas", "documents", "distances"],
    )
    metas = (res.get("metadatas") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    matches: list[dict] = []
    for meta, doc, dist in zip(metas, docs, dists):
        # Chroma cosine 空间 distance = 1 - cosine; 归一化向量下与 Milvus COSINE
        # 度量的 distance 语义一致, similarity 截断 [0,1] 对齐融合与展示。
        similarity = round(max(0.0, min(1.0, 1.0 - float(dist))), 4)
        matches.append({
            "law_name": meta.get("law_name"),
            "article": meta.get("article"),
            "content": doc,
            "keywords": meta.get("keywords"),
            "category": meta.get("category"),
            "score": similarity,
        })
    return matches
