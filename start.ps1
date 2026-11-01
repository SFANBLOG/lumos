# ============================================================
# Lumos 一键启动脚本 (Windows / PowerShell)
# 用法: 在 lumos 目录下, 右键本文件 -> 用 PowerShell 运行
# 说明: 构建并拉起全栈 (mysql + minio + backend + front)
# ============================================================
$ErrorActionPreference = 'Continue'

# 确保 docker 在 PATH 中 (Docker Desktop 默认安装路径)
$env:PATH += ";C:\Users\Administrator\AppData\Local\Programs\DockerDesktop\resources\bin"

# 切换到脚本所在目录 (即 lumos 项目根)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "==> 检查 Docker 守护进程"
docker version --format "server={{.Server.Version}}" 2>&1

Write-Host "==> 构建并启动 Lumos 全栈 (mysql + minio + backend + front)"
Write-Host "    (首次构建 backend 镜像时, torch CPU wheel 从阿里云镜像拉取, 约需 5-15 分钟)"
docker compose up -d --build

Write-Host "==> 容器状态"
docker compose ps

Write-Host ""
Write-Host "    前端:    http://localhost:8080"
Write-Host "    后端API: http://127.0.0.1:8001"
Write-Host "    MinIO:   http://localhost:9003 (控制台) / :9002 (API)"
