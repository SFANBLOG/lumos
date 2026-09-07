# Lumos Server

Lumos · 契光鉴微 Python 后端服务。

## 技术栈

- FastAPI / uvicorn
- JWT + API Key 认证
- Supervisor + 子智能体 (Multi-Agent)
- LangChain / OpenAI SDK
- Milvus / ChromaDB 向量检索
- MinIO 对象存储
- SQLModel + aiomysql (MySQL/SQLite)
- MCP (Model Context Protocol)

## 快速开始

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# 编辑 .env 填入 AI API Key
uvicorn app.main:app --reload --port 8000
```

## 主要模块

- `app/agent/` — Multi-Agent 分析引擎
- `app/api/v1/` — REST API
- `app/mcp/` — MCP 工具服务
- `app/rag/` — 向量检索 (Milvus/ChromaDB)
- `app/skills/` — 可复用技能
- `app/middleware/` — 中间件
- `app/models/` — 数据模型

## API 概览

| 方法 | 端点 | 描述 |
|:---|:---|:---|
| `POST` | `/api/v1/auth/register` | 用户注册 |
| `POST` | `/api/v1/auth/login` | 用户登录 |
| `GET` | `/api/v1/auth/me` | 当前用户信息 |
| `POST` | `/api/v1/contracts` | 提交合同分析 |
| `GET` | `/api/v1/contracts/{id}/stream` | SSE 流式分析 |
| `GET` | `/api/v1/contracts/{id}/report` | 获取完整报告 |
| `GET` | `/api/v1/mcp/tools` | 列出 MCP 工具 |
| `POST` | `/api/v1/mcp/tools/call` | 调用 MCP 工具 |
| `POST` | `/api/v1/ingest/file` | 上传文件并抽取文本 (10 种格式) |
| `POST` | `/api/v1/ingest/url` | 抓取网页链接并抽取正文 |
| `POST` | `/api/v1/consult/ask` | 智能咨询 (SSE 流式) |
| `GET` | `/api/v1/consult/sessions` | 咨询会话列表 |
| `GET` | `/api/v1/consult/sessions/{id}/messages` | 会话消息记录 |
