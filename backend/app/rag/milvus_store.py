"""
Milvus 向量库封装.

替代 ChromaDB，用于存储劳动法条文的向量表示，支持语义检索。
"""

from __future__ import annotations

from functools import lru_cache

from loguru import logger
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.core.config import get_settings
from app.rag.law_corpus import ALL_LAWS

settings = get_settings()

_DIM = 384  # all-MiniLM-L6-v2 维度 (后续可配置)


def _connect() -> None:
    """建立 Milvus 连接."""
    connections.connect(
        alias="default",
        host=settings.milvus_host,
        port=settings.milvus_port,
    )


@lru_cache
def get_milvus_collection() -> Collection:
    """获取或创建法律条文集合."""
    _connect()

    collection_name = settings.milvus_collection
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="law_name", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="article", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="keywords", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=_DIM),
    ]
    schema = CollectionSchema(fields, description="劳动法条文向量库")

    if collection_name not in utility.list_collections():
        collection = Collection(name=collection_name, schema=schema)
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            "params": {"nlist": 128},
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        collection.load()
        logger.info(f"🆕 Milvus 集创建: {collection_name}")
    else:
        collection = Collection(collection_name)
        collection.load()

    return collection


def _simple_embedding(texts: list[str]) -> list[list[float]]:
    """占位 embedding: 随机向量 (生产环境应使用 sentence-transformers 或 API)."""
    import random

    random.seed(42)
    return [[random.uniform(-1, 1) for _ in range(_DIM)] for _ in texts]


def init_milvus() -> None:
    """加载法条到 Milvus."""
    try:
        collection = get_milvus_collection()
        if collection.num_entities > 0:
            logger.info(f"✅ Milvus 已就绪 | 条文: {collection.num_entities} 条")
            return

        contents = []
        law_names = []
        articles = []
        keywords = []
        categories = []
        for law in ALL_LAWS:
            contents.append(law["content"])
            law_names.append(law["law_name"])
            articles.append(law["article"])
            categories.append(law.get("category", ""))
            keywords.append(", ".join(law.get("keywords", [])))

        embeddings = _simple_embedding(contents)

        collection.insert(
            [
                law_names,
                articles,
                contents,
                keywords,
                categories,
                embeddings,
            ]
        )
        collection.flush()
        logger.info(f"✅ Milvus 加载完成 | 条文: {len(contents)} 条")
    except Exception as e:
        logger.error(f"❌ Milvus 初始化失败: {e}")
        raise


def search_milvus(
    query: str,
    n_results: int = 5,
    category: str | None = None,
) -> list[dict]:
    """语义检索法律条文."""
    collection = get_milvus_collection()
    query_vector = _simple_embedding([query])

    search_params = {"metric_type": "L2", "params": {"nprobe": 16}}
    results = collection.search(
        data=query_vector,
        anns_field="embedding",
        param=search_params,
        limit=n_results,
        output_fields=["law_name", "article", "content", "keywords", "category"],
    )

    matches = []
    for result in results[0]:
        entity = result.entity
        if category and entity.get("category") != category:
            continue
        matches.append({
            "law_name": entity.get("law_name"),
            "article": entity.get("article"),
            "content": entity.get("content"),
            "keywords": entity.get("keywords"),
            "category": entity.get("category"),
            "similarity": 1 / (1 + result.distance),
        })
    return matches
