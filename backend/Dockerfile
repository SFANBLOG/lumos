# ========================================
# Lumos Server — 多阶段构建 Dockerfile
# ========================================
# 使用 uv 加速 Python 依赖安装

# ---- 阶段 1: 构建 ----
FROM python:3.12-slim AS builder

# 国内镜像加速 (清华 PyPI): pip / uv 走清华源, 避免默认 PyPI 在本环境拉取缓慢
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 先复制依赖声明 (利用 Docker 层缓存)
COPY pyproject.toml ./

# 安装 uv: 改用 pip 从国内源安装, 避免从 ghcr.io 拉取 uv 镜像 (本环境 ghcr 极慢)
RUN pip install --no-cache-dir uv

# torch 的纯 Python 依赖 (如 markupsafe) 在 pytorch 官方索引缺失, 先从清华 PyPI 预装, 避免解析中断
RUN uv pip install --system --no-cache jinja2 markupsafe
# 装 CPU 版 torch: 使用阿里云 pytorch CPU wheel 镜像 (国内 CDN, 稳定且快, 远优于官方源);
# 本服务纯 CPU 推理, 避免拉取 2.5GB 的 NVIDIA CUDA 运行库. torch 从阿里云 find-links 取 (+cpu 优先于 PyPI 的 plain 版),
# 其余依赖 (sympy/networkx/jinja2...) 走清华 PyPI (UV_INDEX_URL)
RUN uv pip install --system --no-cache torch --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu
# 再装其余依赖 (torch 已满足 sentence-transformers 约束, 不会重复拉取 CUDA 版)
RUN uv pip install --system --no-cache -r pyproject.toml

# ---- 阶段 2: 运行 ----
FROM python:3.12-slim AS runtime

# 系统依赖: Tesseract OCR (图片上传走 OCR 抽取文字, 含中文语言包)
# 改用清华 Debian 镜像源加速 apt。Debian trixie 默认使用 deb822 格式
# (/etc/apt/sources.list.d/debian.sources); 旧版则在 /etc/apt/sources.list。两者都处理。
RUN sed -i \
      -e 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' \
      -e 's|https://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' \
      -e 's|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
      -e 's|https://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
      /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    sed -i \
      -e 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' \
      -e 's|https://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' \
      -e 's|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
      -e 's|https://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
      /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从 builder 阶段复制已安装的包
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用代码
COPY . .

# 非 root 用户运行
RUN groupadd -r lumos && useradd -r -g lumos lumos \
    && mkdir -p /home/lumos && chown -R lumos:lumos /home/lumos
ENV HOME=/home/lumos
USER lumos

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health')" || exit 1

# 启动命令 (单 worker: 分析任务事件缓冲为进程内状态)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
