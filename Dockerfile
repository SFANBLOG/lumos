# ========================================
# Lumos Server — PocketBay 单容器根级 Dockerfile
# ========================================
# 方案 A: 单容器同时跑前端(nginx) + 后端(uvicorn)
# 适用: PocketBay / Render / Fly.io 等单 deploy type 单容器平台
#
# 运行架构:
#   ${PORT} (PocketBay 注入, 默认 8080)  →  nginx
#                                              ├─ /api/* → 127.0.0.1:8000  (uvicorn)
#                                              └─ /*     → /usr/share/nginx/html (Vue 静态)
#   8000                                  →  uvicorn (FastAPI)
#
# 两个进程由 supervisord 同时管理, 任一崩溃自动重启

# ========================================
# Stage 1: 前端构建
# ========================================
FROM node:20-alpine AS frontend-builder

WORKDIR /web

# 先复制 manifest 充分利用 Docker 缓存
COPY front/package.json front/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

# 复制源码 + 构建
COPY front/ ./
RUN npm run build


# ========================================
# Stage 2: 后端依赖 (利用 uv 加速)
# ========================================
FROM python:3.11-slim AS backend-builder

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# 先复制依赖清单, 利用缓存
COPY backend/pyproject.toml ./
COPY backend/README.md ./README.md
# hatchling 需要包源码才能构建项目本身；先复制最小应用目录，避免
# `uv pip install .` 在 PocketBay 构建阶段因找不到 app 包而失败。
COPY backend/app/ ./app/

# CPU 版 torch (避免拉 2.5GB NVIDIA CUDA 库)
RUN uv pip install --system --no-cache torch --index-url https://download.pytorch.org/whl/cpu
# 项目依赖
RUN uv pip install --system --no-cache .


# ========================================
# Stage 3: 运行镜像 (nginx + uvicorn + supervisord)
# ========================================
FROM python:3.11-slim AS runtime

# 系统依赖: Tesseract OCR (中文), nginx, supervisor, gettext-base (envsubst)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx \
        supervisor \
        gettext-base \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段复制 Python 依赖
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

WORKDIR /app

# 复制后端代码
COPY backend/ ./

# 复制前端构建产物 + PocketBay 专用 nginx 配置
COPY --from=frontend-builder /web/dist /usr/share/nginx/html
COPY deploy/nginx.pocketbay.conf /etc/nginx/conf.d/default.conf

# 复制 supervisord + entrypoint
COPY deploy/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 创建非 root 后端运行用户；nginx 仍需要 root 绑定平台端口，
# supervisord 会按各 program 的 user 设置分别降权。
RUN groupadd -r lumos && useradd -r -g lumos -m lumos \
    && mkdir -p /home/lumos /var/log/supervisor /var/log/nginx /var/lib/nginx \
                /run/nginx /app/logs /tmp/nginx \
    && chown -R lumos:lumos /home/lumos /app /var/log/supervisor /var/log/nginx \
                          /var/lib/nginx /run/nginx /tmp/nginx /usr/share/nginx/html
# 端口说明:
#   8000  — uvicorn (容器内)
#   ${PORT:-8080} — nginx (PocketBay 暴露)
EXPOSE 8080 8000

# 健康检查 (PocketBay 会执行)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8080}/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
