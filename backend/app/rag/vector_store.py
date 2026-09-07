"""
向量数据库管理 (兼容层).

优先使用 Milvus；Milvus 不可用时降级到 ChromaDB。
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.core.config import get_settings
from app.rag.law_corpus import ALL_LAWS

settings = get_settings()


def _get_chroma_path() -> str:
    """获取 ChromaDB 持久化路径."""
    base = Path(settings.database_url.split("///")[-1]).parent if ":///" in settings.database_url else Path(".")
    chroma_dir = base / "chroma_db"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return str(chroma_dir)


@lru_cache
def get_chroma_client() -> chromadb.ClientAPI:
    """获取 ChromaDB 客户端 (单例)."""
    chroma_path = _get_chroma_path()
    logger.info(f"📦 ChromaDB 路径: {chroma_path}")

    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return client


def _compute_corpus_hash() -> str:
    """计算法条库的内容哈希，用于判断是否需要重新加载."""
    content = json.dumps(ALL_LAWS, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(content.encode()).hexdigest()[:12]  # noqa: S324


def get_law_collection() -> chromadb.Collection:
    """获取或创建法律条文集合."""
    client = get_chroma_client()
    collection_name = "labor_laws"

    try:
        collection = client.get_collection(collection_name)
        metadata = collection.metadata or {}

        current_hash = _compute_corpus_hash()
        if metadata.get("corpus_hash") == current_hash:
            logger.info(f"✅ 法律向量库已是最新 | 条文: {collection.count()} 条")
            return collection

        logger.info(" 法条库已更新，重新加载向量…")
        client.delete_collection(collection_name)
    except Exception:
        logger.info("🆕 首次创建法律向量库…")

    return _build_collection(client, collection_name)


def _build_collection(client: chromadb.ClientAPI, name: str) -> chromadb.Collection:
    """构建法律条文向量集合."""
    corpus_hash = _compute_corpus_hash()

    collection = client.create_collection(
        name=name,
        metadata={
            "description": "中国劳动法核心条文知识库",
            "corpus_hash": corpus_hash,
            "hnsw:space": "cosine",
        },
    )

    documents = []
    metadatas = []
    ids = []

    for i, law in enumerate(ALL_LAWS):
        doc_text = (
            f"《{law['law_name']}》{law['article']}\n"
            f"{law['content']}\n"
            f"关键词: {', '.join(law['keywords'])}"
        )
        documents.append(doc_text)
        metadatas.append({
            "law_name": law["law_name"],
            "article": law["article"],
            "category": law.get("category", ""),
            "keywords": ", ".join(law["keywords"]),
        })
        ids.append(f"law_{i:04d}")

    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )

    logger.info(f"✅ 法律向量库构建完成 | 共 {len(documents)} 条法条")
    return collection


def search_laws(
    query: str,
    n_results: int = 5,
    category: str | None = None,
) -> list[dict]:
    """
    语义检索相关法律条文.

    优先使用 Milvus；不可用时降级到 ChromaDB。
    """
    try:
        from app.rag.milvus_store import search_milvus

        return search_milvus(query, n_results=n_results, category=category)
    except Exception as e:
        logger.warning(f"Milvus 检索失败，降级 ChromaDB: {e}")
        return _search_chroma(query, n_results, category)


def _search_chroma(
    query: str,
    n_results: int,
    category: str | None,
) -> list[dict]:
    collection = get_law_collection()
    where = {"category": category} if category else None

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    matches = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        similarity = 1 - (distance / 2)
        matches.append({
            "law_name": meta["law_name"],
            "article": meta["article"],
            "content": doc.split("\n")[1] if "\n" in doc else doc,
            "keywords": meta.get("keywords", ""),
            "category": meta.get("category", ""),
            "similarity": round(similarity, 4),
        })

    return matches


def init_vector_store() -> None:
    """初始化向量库 (应用启动时调用)."""
    try:
        from app.rag.milvus_store import init_milvus

        init_milvus()
    except Exception as e:
        logger.warning(f"Milvus 不可用，使用 ChromaDB: {e}")
        get_law_collection()
        logger.info("⚖️ ChromaDB 法律向量库就绪")
