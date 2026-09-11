"""
Milvus 向量库封装 (混合检索的向量通道).

使用新版 ``MilvusClient`` 客户端 API (PyMilvus 3.x 推荐写法),
避免 ORM-style ``Collection.num_entities`` / ``Collection.insert`` /
``Collection.flush`` 等将在 3.1 移除的接口触发 DeprecationWarning。

- 向量由真实 embedding 模型产出 (见 ``app.rag.embeddings``), 非占位随机向量;
- 度量统一为 COSINE (向量已归一化), 检索返回余弦相似度;
- 集合名 = 基名 + embedding 签名后缀, 切换模型/通道时自动隔离重建,
  避免不同向量空间的数据混在同一集合中。
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from loguru import logger
from pymilvus import DataType, MilvusClient

from app.core.config import get_settings
from app.rag.embeddings import embedding_dim, embedding_signature, embed_query, embed_texts
from app.rag.law_corpus import ALL_LAWS

settings = get_settings()


def collection_full_name() -> str:
    """实际集合名: 基名 + embedding 签名哈希 (8 位)."""
    sig_hash = hashlib.sha256(embedding_signature().encode("utf-8")).hexdigest()[:8]
    return f"{settings.milvus_collection}_{sig_hash}"


@lru_cache
def get_milvus_client() -> MilvusClient:
    """获取 (缓存) Milvus 客户端连接."""
    return MilvusClient(host=settings.milvus_host, port=str(settings.milvus_port))


def _drop_legacy_collection(client: MilvusClient, full_name: str) -> None:
    """清理旧版同名集合 (无签名后缀, 由占位向量时代的代码创建)."""
    base = settings.milvus_collection
    if base != full_name and client.has_collection(base):
        logger.warning(f"🧹 检测到旧版集合 {base} (占位向量时代产物), 自动删除")
        client.drop_collection(base)


def _build_schema_and_index(dim: int) -> tuple:
    """构建集合 Schema 与索引参数 (MilvusClient 客户端 API)."""
    schema = get_milvus_client().create_schema(auto_id=True)
    schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
    schema.add_field("law_name", DataType.VARCHAR, max_length=128)
    schema.add_field("article", DataType.VARCHAR, max_length=128)
    schema.add_field("content", DataType.VARCHAR, max_length=4096)
    schema.add_field("keywords", DataType.VARCHAR, max_length=1024)
    schema.add_field("category", DataType.VARCHAR, max_length=128)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)

    index_params = get_milvus_client().prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": 128},
    )
    return schema, index_params


def _corpus_drifted(client: MilvusClient, name: str) -> bool:
    """语料漂移检测: 条数不一致或首条内容不一致时重建."""
    try:
        stats = client.get_collection_stats(name)
        row_count = int(stats.get("row_count", 0))
    except Exception:  # noqa: BLE001
        return True
    if row_count != len(ALL_LAWS):
        return True
    first = client.query(
        collection_name=name, filter="id > 0", limit=1,
        output_fields=["law_name", "content"],
    )
    if not first:
        return True
    sample = ALL_LAWS[0]
    hit = first[0]
    return (
        hit.get("law_name") != sample["law_name"]
        or hit.get("content") != sample["content"]
    )


def ensure_milvus_collection() -> str:
    """确保集合存在 (必要时创建/重建), 返回集合名."""
    client = get_milvus_client()
    name = collection_full_name()
    dim = embedding_dim()
    _drop_legacy_collection(client, name)

    if client.has_collection(name):
        # 已存在: 先加载再判断是否需重建 (语料/embedding 变化时)
        try:
            client.load_collection(name)
        except Exception:  # noqa: BLE001  # 已加载/不存在索引时忽略
            pass
        if _corpus_drifted(client, name):
            logger.info(f"🔄 法条语料/embedding 已变化, 重建集合: {name}")
            try:
                client.release_collection(name)
            except Exception:  # noqa: BLE001
                pass
            client.drop_collection(name)
            schema, index_params = _build_schema_and_index(dim)
            client.create_collection(
                collection_name=name, schema=schema, index_params=index_params,
            )
        else:
            stats = client.get_collection_stats(name)
            row_count = int(stats.get("row_count", 0))
            logger.info(
                f"✅ Milvus 集合就绪 | {name} | dim={dim} | {row_count} 条"
            )
    else:
        schema, index_params = _build_schema_and_index(dim)
        client.create_collection(
            collection_name=name, schema=schema, index_params=index_params,
        )
        logger.info(f"🆕 Milvus 集创建: {name} | dim={dim}")

    return name


def init_milvus() -> None:
    """将法条语料向量化写入 Milvus (幂等)."""
    try:
        client = get_milvus_client()
        name = ensure_milvus_collection()

        stats = client.get_collection_stats(name)
        row_count = int(stats.get("row_count", 0))
        if row_count > 0:
            logger.info(f"✅ Milvus 已就绪 | 条文: {row_count} 条")
            return

        # 准备数据 (MilvusClient 接受行式 dict 列表)
        texts: list[str] = []
        rows: list[dict] = []
        for law in ALL_LAWS:
            keywords_str = ", ".join(law.get("keywords", []))
            # 向量化文本 = 法条全文 (名称/编号/正文/关键词), 与 BM25 文档同构
            texts.append(
                f"{law['law_name']} {law['article']} {law['content']} {keywords_str}"
            )
            rows.append({
                "law_name": law["law_name"],
                "article": law["article"],
                "content": law["content"],
                "keywords": keywords_str,
                "category": law.get("category", ""),
                "embedding": None,  # 占位, 下面统一填充
            })

        logger.info(f"🧠 向量化 {len(texts)} 条法条 (模型: {embedding_signature()})…")
        vectors = embed_texts(texts)
        for row, vec in zip(rows, vectors):
            row["embedding"] = vec

        client.insert(collection_name=name, data=rows)
        client.flush(collection_name=name)
        logger.info(f"✅ Milvus 加载完成 | 条文: {len(rows)} 条 | dim={len(vectors[0])}")
    except Exception as e:
        logger.error(f"❌ Milvus 初始化失败: {e}")
        raise


def search_milvus(
    query: str,
    n_results: int = 5,
    category: str | None = None,
) -> list[dict]:
    """向量通道语义检索 (余弦相似度降序)."""
    client = get_milvus_client()
    name = collection_full_name()
    query_vector = embed_query(query)

    filter_expr = f'category == "{category}"' if category else ""
    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}
    results = client.search(
        collection_name=name,
        data=[query_vector],
        anns_field="embedding",
        limit=n_results,
        filter=filter_expr,
        output_fields=["law_name", "article", "content", "keywords", "category"],
        search_params=search_params,
    )

    matches: list[dict] = []
    for hit in results[0]:
        # MilvusClient 返回扁平 dict (output_fields 直接在 hit 里);
        # COSINE 度量的 distance 字段即余弦相似度 (值域 [-1,1], 越大越相似,
        # 官方口径: "A greater value indicates a greater similarity"),
        # 归一化向量下数值稳定; 截断到 [0,1] 供融合与相关度展示。
        similarity = round(max(0.0, min(1.0, float(hit.get("distance", 0.0)))), 4)
        matches.append({
            "law_name": hit.get("law_name"),
            "article": hit.get("article"),
            "content": hit.get("content"),
            "keywords": hit.get("keywords"),
            "category": hit.get("category"),
            "score": similarity,
        })
    return matches