"""
应用全局配置.

使用 pydantic-settings 从环境变量/.env 文件自动加载配置，
支持 development / production / testing 三种模式。
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录 = backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Environment(str, Enum):
    """运行环境枚举."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """应用核心配置, 一切可配项均在此定义."""

    model_config = SettingsConfigDict(
        # 本地读 backend/.env; PocketBay 把批准的配置挂载到 backend/.env (容器内即 /app/backend/.env)
        env_file=(str(BASE_DIR / ".env"), str(BASE_DIR / "backend" / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 应用基础 ──────────────────────────────────────────────
    app_name: str = "Lumos Server"
    app_version: str = "0.2.0"
    app_env: Environment = Environment.DEVELOPMENT
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    # 逗号分隔。生产环境务必只填写实际的前端域名；同域部署可以留空。
    cors_origins: str = ""
    trusted_hosts: str = "*"
    # 首个企业管理员白名单（逗号分隔）；匹配邮箱注册后自动授予 owner。
    bootstrap_owner_emails: str = ""

    # ── 数据库 (MySQL) ────────────────────────────────────────
    database_url: str = "mysql+aiomysql://lumos:lumos@localhost:3306/lumos"
    # 是否回显执行 SQL (调试用; 默认关闭, 避免控制台/日志被 SELECT 刷屏)
    database_echo: bool = False

    # ── LangGraph 断点续跑 checkpointer ──────────────────────
    # 工作流状态持久化后端: postgres (AsyncPostgresSaver, 生产, 支持中断续跑/重放)
    #                      | memory  (进程内存, 重启丢失, 仅用于本地/测试)
    # 切到 memory 可零依赖验证断点续跑机制; 生产务必用 postgres
    checkpoint_backend: str = "postgres"
    # Postgres 连接串 (psycopg 格式); 仅 checkpoint_backend=postgres 时使用。
    # 注: LangGraph PostgresSaver 基于 psycopg (非 asyncpg), 需 psycopg[binary] 依赖
    checkpoint_postgres_dsn: str = "postgresql://lumos:lumos@localhost:5432/lumos"

    # ── AI 模型 ───────────────────────────────────────────────
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model_name: str = "deepseek-chat"

    # 嵌入模型 (RAG 真实 embedding)
    # provider: local(默认, sentence-transformers 本地模型) | api(OpenAI 兼容 /embeddings)
    # 注意: 切换到不同模型/通道后向量索引会按签名自动重建
    embedding_provider: str = "local"
    embedding_model_name: str = "BAAI/bge-base-zh-v1.5"
    embedding_base_url: str = "https://api.deepseek.com/v1"
    embedding_api_key: str = ""
    # 手动指定向量维度; 留空则由模型自动探测 (首次加载后确定)
    embedding_dim: int | None = None
    # 检索 query 前缀指令 (BGE 系列建议 query 加指令、文档不加; 留空=按模型自动适配)
    embedding_query_instruction: str = ""

    # ── 混合检索 (Milvus 向量 + BM25 + RRF 融合) ──────────────
    hybrid_top_k_ratio: int = 2  # 融合前各通道候选数 = top_k × 该值
    rrf_k: int = 60  # RRF 融合参数: score = Σ 1/(k + rank)
    # 相关度分数 (similarity) 口径: 双通道命中 = 向量权重·余弦相似度 +
    # (1-向量权重)·BM25归一; 仅单通道命中时再乘折扣因子
    hybrid_vector_weight: float = 0.65  # 向量通道权重 (0~1, BM25 权重为其补数)
    hybrid_single_channel_factor: float = 0.85  # 单通道命中的相关度折扣 (0~1)
    # ── 重排 / 精排 ───────────────────────────────────────────
    # 先以轻量可解释精排收敛 RRF 候选；生产可开启 CrossEncoder 进一步做语义重排。
    reranker_enabled: bool = False
    reranker_model_name: str = "BAAI/bge-reranker-base"
    reranker_candidate_multiplier: int = 3
    reranker_max_length: int = 512
    retrieval_min_similarity: float = 0.05

    # ── 多模态视觉模型 (图片/扫描件 OCR) ─────────────────────
    # 复用 OpenAI 兼容接口; DeepSeek 无视觉能力, 默认走通义千问 VL (DashScope 兼容模式)。
    # 视觉模型使用独立密钥; 未配置 llm_vision_api_key 时图片自动回退本地 Tesseract OCR。
    llm_vision_api_key: str = ""
    llm_vision_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_vision_model_name: str = "qwen-vl-max-latest"
    image_ocr_strategy: str = "auto"  # auto | llm | tesseract
    # 扫描版/文字层 PDF 的跨页表格自动检测与合并 (见 app/services/table_merge.py)
    # 关闭后恢复"逐页独立抽取", 跨页表会被切成两张半张表
    pdf_cross_page_table_merge: bool = True
    # 跨页判定的"版面 y 坐标连续性"信号 (见 app/services/table_layout.py)
    # 开: 有文字层页用 PyMuPDF 矢量线框, 扫描页复用已渲染位图跑 Tesseract 词框;
    # 关: 只用纯文本信号 (表头/列数/截断/表题)。几何拿不到时也会自动退回纯文本
    pdf_layout_geometry: bool = True
    # 同页多栏(双栏/分栏)的栏感知抽取: 检测栏边界后按"先栏后 y"重组文本块,
    # 避免跨栏文本把同栏内的表格行切断; 仅对"检测到多栏"的页启用, 单栏/无
    # PyMuPDF 时完全走原抽取路径, 不会退化
    pdf_column_aware_extract: bool = True

    # ── 安全 ──────────────────────────────────────────────────
    api_secret_key: str = ""
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 天

    # ── Milvus ───────────────────────────────────────────────
    # 两套连接模式, 通过 MILVUS_USE_URI 切换:
    #   - false (默认, 本地/单机): 用 MILVUS_HOST + MILVUS_PORT 连接 (如 localhost:19530)
    #   - true (托管/Serverless): 用 MILVUS_URI + MILVUS_TOKEN 连接 (如 Zilliz Cloud)
    milvus_use_uri: bool = False
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_uri: str = ""  # 例: https://in01-xxxx.zillizcloud.com
    milvus_token: str = ""  # Zilliz Cloud: api key; 用户名:密码 也可
    # 基集合名; 实际集合名 = 基名 + embedding 签名后缀, 换模型自动隔离重建
    milvus_collection: str = "labor_laws"

    # ── 向量通道降级备库 (Chroma) ───────────────────────────
    # Milvus 不可用时由本地嵌入式 Chroma (PersistentClient) 兜底语义检索,
    # 避免退化为仅 BM25 关键词检索; 两者均不可用向量通道才关闭。
    chroma_enabled: bool = True  # 关闭则 Milvus 故障时向量通道直接关闭 (无 Chroma 兜底)
    chroma_persist_dir: str = "data/chroma"  # 本地持久化目录 (相对 backend 根)
    chroma_collection: str = "lumos_laws"  # 基集合名 (实际 = 基名 + embedding 签名后缀)

    # ── MinIO ─────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "lumos"
    minio_secure: bool = False
    # 外部依赖不可用时的连接超时；避免开发机未启动容器时阻塞应用启动。
    dependency_connect_timeout_seconds: float = 2.0
    dependency_read_timeout_seconds: float = 5.0

    # ── A2A (Agent2Agent Protocol) ───────────────────────────
    # 将 Lumos 暴露为标准 A2A Agent, 供其他 Agent 发现并调用。
    a2a_enabled: bool = True
    # 对外可访问的 A2A 基址 (含协议与域名); 留空则回退到 app_host:app_port
    # (容器内常为 0.0.0.0 不可路由, 生产务必显式配置, 如 https://lumos.example.com)。
    a2a_public_url: str = ""
    # A2A JSON-RPC 端点路径 (Agent Card 的 url 据此拼接)。
    a2a_base_path: str = "/a2a"

    # ── 日志 ──────────────────────────────────────────────────
    log_level: str = "DEBUG"

    # ── 衍生属性 ──────────────────────────────────────────────
    @property
    def is_development(self) -> bool:
        return self.app_env == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.app_env == Environment.TESTING

    @property
    def auth_enabled(self) -> bool:
        """只在 api_secret_key 非空时启用鉴权."""
        return bool(self.api_secret_key)

    @property
    def cors_origin_list(self) -> list[str]:
        """将环境变量中的逗号分隔来源解析为 CORS 白名单。"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        """将受信任 Host 配置解析为 Starlette 可用的列表。"""
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def bootstrap_owner_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.bootstrap_owner_emails.split(",") if email.strip()}


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例 (缓存)."""
    return Settings()
