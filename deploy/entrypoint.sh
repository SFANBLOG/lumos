#!/bin/bash
# ========================================
# PocketBay 容器入口脚本
# ========================================
# 职责:
#   1. 处理 PORT 环境变量 (PocketBay / Render 注入)
#   2. 把 PORT 注入 nginx 配置 (envsubst)
#   3. 检查必要环境变量 (DATABASE_URL / DEEPSEEK_API_KEY 等)
#   4. 启动 supervisord

set -e

# ---- 1. 处理 PORT ----
export PORT="${PORT:-8080}"
echo "🌐 PORT=$PORT"

# ---- 2. 把 ${PORT} 替换到 nginx 配置 ----
# 复制模板到 nginx 默认位置, 再 envsubst 替换环境变量
envsubst '${PORT}' < /etc/nginx/conf.d/default.conf > /etc/nginx/conf.d/default.conf.rendered
mv /etc/nginx/conf.d/default.conf.rendered /etc/nginx/conf.d/default.conf

# ---- 3. 检查必填环境变量 ----
if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  DATABASE_URL 未设置, 关系型功能将不可用 (注册/登录/会话将失败)"
fi

if [ -z "$LLM_API_KEY" ]; then
    echo "⚠️  LLM_API_KEY 未设置, 合同分析/智能咨询将不可用"
fi

if [ -z "$MINIO_ACCESS_KEY" ] || [ -z "$MINIO_SECRET_KEY" ]; then
    echo "⚠️  MINIO_* 未设置, 文件上传将不可用"
fi

# ---- 4. 启动 supervisord (前台进程, 会接管 PID 1) ----
echo "🚀 启动 supervisord (uvicorn + nginx)"
exec "$@"
