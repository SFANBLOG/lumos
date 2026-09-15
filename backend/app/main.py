"""
Lumos Server — FastAPI 应用入口.

🔍 契光鉴微 · AI 合同风险排查引擎
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许直接 `python app/main.py` 启动：将 backend/ 加入模块搜索路径
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import setup_logging
from app.middleware import register_middleware
from app.rag.vector_store import init_vector_store


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理."""
    # ── 启动 ──
    setup_logging()
    settings = get_settings()

    logger.info("=" * 60)
    logger.info(f"🔍 {settings.app_name} v{settings.app_version}")
    logger.info(f"📍 环境: {settings.app_env.value}")
    logger.info(f"🗄️ 数据库: {settings.database_url[:50]}...")
    logger.info(f"🤖 LLM: {settings.llm_model_name} @ {settings.llm_base_url[:40]}")
    logger.info(f"🔐 鉴权: {'已启用' if settings.auth_enabled else '未启用'}")
    logger.info("=" * 60)

    # 初始化数据库 (MySQL 不可用时仅告警并继续启动, 关系型功能将降级)
    try:
        await init_db()
        logger.info("✅ 数据库初始化完成")
    except Exception as e:  # noqa: BLE001
        logger.error(f"❌ 数据库初始化失败 (关系型功能将不可用, 请检查 DATABASE_URL/MySQL): {e}")

    # 初始化向量库 (后台执行: 加载本地 embedding 模型 + 写入 Milvus 可能耗时较长,
    # 不阻塞服务启动; /health 立即可用, 向量通道在模型就绪后自动上线)
    import asyncio

    asyncio.create_task(asyncio.to_thread(init_vector_store))

    # 初始化 MCP 服务端
    from app.mcp.server import get_mcp_server
    get_mcp_server()

    # 初始化技能注册中心
    from app.skills import list_skills
    logger.info(f"🛠️ 技能列表: {list_skills()}")

    # 初始化 MinIO
    from app.core.minio_client import init_minio
    init_minio()

    logger.info(f"🚀 服务已启动: http://{settings.app_host}:{settings.app_port}")
    logger.info(f"📚 API 文档: http://{settings.app_host}:{settings.app_port}/docs")

    yield

    # ── 关闭 ──
    logger.info("👋 服务正在关闭…")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "🔍 **Lumos · 契光鉴微** — AI 合同风险排查引擎\n\n"
            "开源免费的劳动合同风险检测服务，站在劳动者视角，\n"
            "深度适配中国劳动法，一键排查合同中的十大坑点。\n\n"
            "---\n"
            "- 📸 拍照即查 (端侧 OCR)\n"
            "- 💬 \"说人话\"的条款解读\n"
            "- 🗣️ 一键生成谈判话术\n"
            "- ⚡ SSE 流式实时分析\n"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── 中间件 (后注册的先执行) ──
    register_middleware(app)

    # ── CORS 跨域 ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else settings.cors_origin_list,
        # 浏览器带凭据时不能使用 CORS 通配符；生产环境只启用显式来源。
        allow_credentials=not settings.is_development and bool(settings.cors_origin_list),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if not settings.is_development and settings.trusted_host_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

    # ── 注册 API 路由 ──
    app.include_router(v1_router)

    # ── 根路径: 服务信息 (替代遗留的 HTML demo 首页) ──
    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "service": settings.app_name,
                "version": settings.app_version,
                "docs": "/docs",
            }
        )

    return app


# 应用实例 (供 uvicorn 直接引用: uvicorn app.main:app)
app = create_app()

# 允许直接 `python main.py` 启动 (免去记 uvicorn 命令)
if __name__ == "__main__":
    import uvicorn

    _settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=_settings.app_host,
        port=_settings.app_port,
        reload=_settings.is_development,
    )
