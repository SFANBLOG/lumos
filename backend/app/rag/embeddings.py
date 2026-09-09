"""
Embedding 提供者 (真实模型, 非占位向量).

支持两种通道, 通过 ``EMBEDDING_PROVIDER`` 切换:
- ``local`` (默认): sentence-transformers 本地模型, 默认
  ``BAAI/bge-base-zh-v1.5`` (768 维, 中文检索友好, 离线可用);
- ``api``: OpenAI 兼容 ``/embeddings`` 接口 (如硅基流动 BAAI/bge-m3 等)。

向量库按 ``embedding_signature()`` 隔离: 切换模型/通道后索引自动重建,
避免不同模型向量混在同一集合中导致检索失真。

BGE 系列检索约定: 仅对 query 追加指令前缀 (文档不做处理),
可显著提升召回精度, 见 ``LocalSentenceTransformerEmbedder.embed_query``。
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from functools import lru_cache

from loguru import logger

from app.core.config import get_settings

_EMBED_BATCH = 32

#: BGE 中文检索 query 指令 (官方推荐; 仅对查询侧生效)
_BGE_QUERY_INSTRUCTION_ZH = "为这个句子生成表示以用于检索相关文章："


class EmbeddingNotReadyError(RuntimeError):
    """embedding 通道不可用 (未安装本地模型依赖或 API Key 未配置)."""


class EmbeddingProvider(ABC):
    """真实 embedding 提供者抽象."""

    #: 通道标识 (如 local / api), 参与索引签名
    provider: str = ""
    #: 模型标识 (本地为 HF 模型名, api 为接口模型名), 参与索引签名
    model_name: str = ""

    def __init__(self) -> None:
        self._dim: int | None = None

    @property
    def signature(self) -> str:
        """索引签名: 不同通道/模型产生不同向量空间, 用于集合隔离."""
        return f"{self.provider}:{self.model_name}"

    @property
    def dim(self) -> int:
        """向量维度 (首次调用时由模型探测)."""
        if self._dim is None:
            self._dim = len(self.embed_texts(["维度探测"])[0])
        return self._dim

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化 (结果已归一化)."""

    def embed_query(self, text: str) -> list[float]:
        """单条查询向量化."""
        return self.embed_texts([text])[0]


class LocalSentenceTransformerEmbedder(EmbeddingProvider):
    """基于 sentence-transformers 的本地模型通道."""

    provider = "local"

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _get_model(self):
        """懒加载模型 (首次调用下载/加载, 线程安全)."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    logger.info(f"🆕 加载本地 embedding 模型: {self.model_name} (首次可能下载)")
                    self._model = SentenceTransformer(self.model_name)
                    logger.info(f"✅ embedding 模型就绪 | {self.model_name} | dim={self.dim}")
        return self._model

    def embed_query(self, text: str) -> list[float]:
        """单条查询向量化.

        BGE 系列模型建议仅对 query 追加指令前缀 (文档不做处理),
        可显著提升语义召回精度; 非 BGE 模型默认不追加。
        """
        instruction = get_settings().embedding_query_instruction
        if not instruction and "bge" in self.model_name.lower():
            instruction = _BGE_QUERY_INSTRUCTION_ZH
        if instruction:
            text = f"{instruction}{text}"
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=_EMBED_BATCH,
            show_progress_bar=False,
        )
        return vectors.tolist()


class ApiEmbedder(EmbeddingProvider):
    """OpenAI 兼容 embedding API 通道."""

    provider = "api"

    def __init__(self, model_name: str, api_key: str, base_url: str) -> None:
        super().__init__()
        self.model_name = model_name
        self._api_key = api_key
        self._base_url = base_url

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        from langchain_openai import OpenAIEmbeddings

        client = OpenAIEmbeddings(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self.model_name,
            check_embedding_ctx_length=False,
        )
        return client.embed_documents(texts)


@lru_cache
def get_embedder() -> EmbeddingProvider:
    """获取 embedding 提供者单例 (按配置的 provider/模型)."""
    settings = get_settings()
    provider = (settings.embedding_provider or "local").strip().lower()
    model_name = settings.embedding_model_name.strip()

    if provider == "local":
        try:
            import sentence_transformers  # noqa: F401  # 仅探测可用性
        except ImportError as e:
            raise EmbeddingNotReadyError(
                "本地 embedding 依赖未安装: pip install -e '.[embedding]' "
                "(或设置 EMBEDDING_PROVIDER=api 使用 API 通道)"
            ) from e
        logger.info(f"🧠 embedding 通道: local | 模型: {model_name}")
        return LocalSentenceTransformerEmbedder(model_name)

    if provider == "api":
        if not settings.embedding_api_key:
            raise EmbeddingNotReadyError(
                "API embedding 通道需要配置 EMBEDDING_API_KEY / "
                "EMBEDDING_BASE_URL / EMBEDDING_MODEL_NAME"
            )
        logger.info(f"🧠 embedding 通道: api | 模型: {model_name} @ {settings.embedding_base_url}")
        return ApiEmbedder(
            model_name=model_name,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
        )

    raise EmbeddingNotReadyError(f"未知 EMBEDDING_PROVIDER: {provider!r} (可选: local | api)")


def embedding_signature() -> str:
    """当前 embedding 索引签名 (provider + 模型名)."""
    return get_embedder().signature


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本向量化 (便捷入口)."""
    return get_embedder().embed_texts(texts)


def embed_query(text: str) -> list[float]:
    """单条查询向量化 (便捷入口)."""
    return get_embedder().embed_query(text)


def embedding_dim() -> int:
    """当前 embedding 维度 (支持配置覆盖)."""
    settings = get_settings()
    if settings.embedding_dim:
        return settings.embedding_dim
    return get_embedder().dim
