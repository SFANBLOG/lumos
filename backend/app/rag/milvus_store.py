"""
Milvus 向量库封装 (混合检索的向量通道).

- 向量由真实 embedding 模型产出 (见 ``app.rag.embeddings``), 非占位随机向量;
- 度量统一为 COSINE (向量已归一化), 检索返回余弦相似度;
- 集合名 = 基名 + embedding 签名后缀, 切换模型/通道时自动隔离重建,
  避免不同向量空间的数据混在同一集合中。
"""

from __future__ import annotations

import hashlib
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
from app.rag.embeddings import embedding_dim, embedding_signature, embed_query, embed_texts
from app.rag.law_corpus import ALL_LAWS

settings = get_settings()


def collection_full_name() -> str:
    """实际集合名: 基名 + embedding 签名哈希 (8 位)."""
    sig_hash = hashlib.sha256(embedding_signature().encode("utf-8")).hexdigest()[:8]
    return f"{settings.milvus_collection}_{sig_hash}"


def _connect() -> None:
    """建立 Milvus 连接."""
    connections.connect(
        alias="default",
        host=settings.milvus_host,
        port=settings.milvus_port,
    )


def _drop_legacy_collection(full_name: str) -> None:
    """清理旧版同名集合 (无签名后缀, 由占位向量时代的代码创建)."""
    base = settings.milvus_collection
    if base != full_name and utility.has_collection(base):
        logger.warning(f"🧹 检测到旧版集合 {base} (占位向量时代产物), 自动删除")
        utility.drop_collection(base)


def _build_schema() -> tuple[CollectionSchema, int]:
    """构建集合 Schema (维度动态取自真实 embedding 模型)."""
    dim = embedding_dim()
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="law_name", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="article", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="keywords", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(fields, description="劳动法条文向量库 (真实 embedding)")
    return schema, dim


def _create_index(collection: Collection) -> None:
    """创建 COSINE 向量索引并加载."""
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 128},
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    collection.load()


def _corpus_drifted(collection: Collection) -> bool:
    """语料漂移检测: 条数不一致或首条内容不一致时重建."""
    if collection.num_entities != len(ALL_LAWS):
        return True
    first = collection.query(expr="id > 0", limit=1, output_fields=["law_name", "content"])
    if not first:
        return True
    sample = ALL_LAWS[0]
    hit = first[0]
    return hit.get("law_name") != sample["law_name"] or hit.get("content") != sample["content"]


@lru_cache
def get_milvus_collection() -> Collection:
    """获取 (必要时创建/重建) 法律条文向量集合."""
    _connect()
    _drop_legacy_collection(collection_full_name())

    name = collection_full_name()
    schema, dim = _build_schema()

    if utility.has_collection(name):
        collection = Collection(name)
        collection.load()
        if _corpus_drifted(collection):
            logger.info(f"🔄 法条语料/embedding 已变化, 重建集合: {name}")
            collection.release()
            utility.drop_collection(name)
            collection = Collection(name, schema=schema)
            _create_index(collection)
        else:
            logger.info(f"✅ Milvus 集合就绪 | {name} | dim={dim} | {collection.num_entities} 条")
    else:
        collection = Collection(name, schema=schema)
        _create_index(collection)
        logger.info(f"🆕 Milvus 集创建: {name} | dim={dim}")

    return collection


def init_milvus() -> None:
    """将法条语料向量化写入 Milvus (幂等)."""
    try:
        collection = get_milvus_collection()
        if collection.num_entities > 0:
            logger.info(f"✅ Milvus 已就绪 | 条文: {collection.num_entities} 条")
            return

        law_names, articles, contents, keywords, categories = [], [], [], [], []
        texts = []
        for law in ALL_LAWS:
            keywords_str = ", ".join(law.get("keywords", []))
            law_names.append(law["law_name"])
            articles.append(law["article"])
            contents.append(law["content"])
            keywords.append(keywords_str)
            categories.append(law.get("category", ""))
            # 向量化文本 = 法条全文 (名称/编号/正文/关键词), 与 BM25 文档同构
            texts.append(
                f"{law['law_name']} {law['article']} {law['content']} {keywords_str}"
            )

        logger.info(f"🧠 向量化 {len(texts)} 条法条 (模型: {embedding_signature()})…")
        vectors = embed_texts(texts)

        collection.insert(
            [law_names, articles, contents, keywords, categories, vectors]
        )
        collection.flush()
        logger.info(f"✅ Milvus 加载完成 | 条文: {len(contents)} 条 | dim={len(vectors[0])}")
    except Exception as e:
        logger.error(f"❌ Milvus 初始化失败: {e}")
        raise


def search_milvus(
    query: str,
    n_results: int = 5,
    category: str | None = None,
) -> list[dict]:
    """向量通道语义检索 (余弦相似度降序)."""
    collection = get_milvus_collection()
    query_vector = embed_query(query)

    expr = f'category == "{category}"' if category else None
    search_params = {
        "metric_type": "COSINE",
        "params": {"nprobe": 16},
    }
    results = collection.search(
        data=[query_vector],
        anns_field="embedding",
        param=search_params,
        limit=n_results,
        expr=expr,
        output_fields=["law_name", "article", "content", "keywords", "category"],
    )

    matches: list[dict] = []
    for result in results[0]:
        entity = result.entity
        # COSINE: distance = 1 - cos_sim; 向量已归一化, 数值稳定
        similarity = round(1.0 - result.distance, 4)
        matches.append({
            "law_name": entity.get("law_name"),
            "article": entity.get("article"),
            "content": entity.get("content"),
            "keywords": entity.get("keywords"),
            "category": entity.get("category"),
            "score": similarity,
        })
    return matches
