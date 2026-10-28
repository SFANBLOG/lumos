# PocketBay 部署准备清单

> **状态：未完成**——LumOS 是 monorepo + 强外部依赖，不能直接打包上传就完事。
> 本文列出**必须先改造**的事项 + **已自动做好的**前置。

---

## 一、PocketBay 平台的硬约束

| 约束 | 说明 |
|---|---|
| 单项目单 deploy type | LumOS 是 monorepo（`backend/` + `front/`），一个 PocketBay 项目只能选 **static / nextjs / node / python / dockerfile** 其一 |
| Dockerfile 必须在项目根 | 当前 backend/Dockerfile 和 front/Dockerfile 在子目录，PocketBay 不会自动找 |
| 不托管 MySQL/Milvus/MinIO/Redis | PocketBay 只托管 Postgres 和无 Redis。LumOS 强依赖 4 个外部服务，**全要换** |
| 监听 PORT 绑 0.0.0.0 | backend 当前 main.py 已 `0.0.0.0:8001`（之前修过端口冲突），需改回 8000 |

**结论**：PocketBay 一键部署 LumOS **当前不可行**，需要先做架构改造。

---

## 二、已自动完成（本会话做的）

| 项 | 文件 | 内容 |
|---|---|---|
| 补 gitignore 漏洞 | `lumos/.gitignore` | 增加 `Agent面试题库.md` 排除（之前漏了） |
| PocketBay 排除清单 | `lumos/.pocketbayignore` | 隐私文件 / 凭据 / 470MB 模型 / 缓存 / 备份等共 7 类约 60 行规则 |
| 部署清单文档 | `lumos/POCKETBAY_DEPLOY.md` | 本文件 |

---

## 三、未完成的改造（待你确认是否推进）

### 决策 1：项目类型 ✅ **已选 A**

| 方案 | 状态 |
|---|---|
| **A. 单 dockerfile 部署 backend+front** | ✅ **已选** —— 已写 `lumos/Dockerfile`（根级）+ `deploy/nginx.pocketbay.conf` + `deploy/supervisord.conf` + `deploy/entrypoint.sh` + `lumos/.dockerignore` |
| B. 拆两个 PocketBay 项目 | 暂不 |
| C. 单 python 类型 | 暂不 |

**方案 A 架构**：
```
${PORT} (默认 8080) → nginx
                        ├─ /api → 127.0.0.1:8000 (uvicorn)
                        ├─ /docs, /openapi.json → 127.0.0.1:8000
                        └─ /* → /usr/share/nginx/html (Vue 静态)
8000 → uvicorn (容器内, 由 supervisord 管理)
```

**Dockerfile 三阶段构建**：
1. `node:20-alpine` 构建前端 `dist/`
2. `python:3.11-slim` + uv 安装后端依赖（CPU 版 torch）
3. `python:3.11-slim` + nginx + supervisord + tesseract-ocr 组合运行镜像

### 决策 2：4 个外部服务的替代 ✅ **已落地（推荐组合）**

| 服务 | 选型 | 代码改动 | 文件 |
|---|---|---|---|
| **MySQL** | PlanetScale (MySQL 兼容) | **零** — 改 `DATABASE_URL` 即可 | `backend/.env` |
| **Milvus** | Zilliz Cloud | 加 `MILVUS_USE_URI=true` 切换分支 | `backend/app/core/config.py` + `backend/app/rag/milvus_store.py` |
| **MinIO → R2** | Cloudflare R2 | **零** — minio SDK S3 协议兼容，改 `MINIO_ENDPOINT` + `MINIO_SECURE=true` | `backend/.env` |
| **Redis** | 当前项目未实际使用 | N/A | — |

**代码验证**：整个 backend 代码 grep `ON DUPLICATE / INSERT IGNORE / LONGTEXT / utf8mb4 / @@ / DATE_FORMAT / TIMESTAMPDIFF / UNIX_TIMESTAMP / NOW()` **零命中**，确认无 MySQL 特定语法，PlanetScale 改 DATABASE_URL 即可。

### 决策 3：embedding 模型 ✅ **已落地**

| 方案 | 状态 |
|---|---|
| ~~保留本地 470MB~~ | ❌ 已弃用 |
| **改 API（硅基流动 bge-m3）** | ✅ `EMBEDDING_PROVIDER=api` + `EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1` + `EMBEDDING_MODEL_NAME=BAAI/bge-m3` |

代码改动：**零**（`backend/app/rag/embeddings.py` 已有完整 local/api 双通道实现），仅在 `.env` 切 `EMBEDDING_PROVIDER=api` 即可。硅基流动免费 200 万 tokens/月，1024 维（比 bge-base-zh 768 维更精细）。

---

## 四、改造后的端到端部署步骤（参考）

> 只有决策 1/2/3 都敲定后才能真正执行。当前**不要直接打包上传**。

1. **你确认决策** → 告诉我选哪个方案
2. **代码改造**（要 1-2 小时）：
   - 替换 MySQL → Postgres（改 DATABASE_URL）
   - 替换 Milvus → Qdrant Cloud 或 Pinecone（改 client）
   - 替换 MinIO → S3 兼容存储（改 endpoint）
   - 改 embedding provider → api
   - 写 `lumos/Dockerfile`（项目根，单容器同时跑 backend+front）
3. **生成 PocketBay 部署包**：
   ```bash
   # PocketBay 流程：AI 打包后自动排除 node_modules/.git/venv/caches
   # .pocketbayignore 进一步排除隐私文件
   zip -r lumos-deploy.zip . -x @.pocketbayignore
   ```
4. **浏览器 pairing**（你手动）：PocketBay 会发一个一次性链接给 AI，AI 转发给你确认
5. **AI 上传**（自动）：打包 → 平台生成 build plan → 健康检查
6. **成功 → pocketbay.app 子域名**；**失败 → 结构化修复提示**

---

## 五、当前可以立即做的（Bash 恢复后）

- [ ] 把 `backend/app/main.py` 的端口写死改回 8000（或仍 8001 + Dockerfile `EXPOSE 8001`）
- [ ] `lumos/Dockerfile` 写根级组合构建
- [ ] 改 `.env` 模板，把所有 `localhost` 改成环境变量占位
- [ ] `backend/app/core/config.py` 加 PocketBay 专用分支（识别 `POCKETBAY_DEPLOY=1`）

---

## 六、风险与建议

| 风险 | 建议 |
|---|---|
| PocketBay 平台未在我知识库（截止 2026-01） | 部署前先用免费档试一次，验证 build plan 是否如手册所述 |
| 单容器跑后端+前端 = 任何 OOM 都会全挂 | production 用 B 方案（拆两个 PocketBay 项目） |
| 模型降级 API 后检索质量变化 | 跑一次 `python -m eval.retrieval_eval` 对比 hit@k |
| 真实凭据一旦部署就泄漏 | 部署后立刻轮换 DeepSeek/MySQL/MinIO 的密钥 |

---

## 七、当前动作建议

**请回到对话告诉我三件事**：

1. **决策 1**：A（单容器 backend+front）/ B（拆两个项目）/ C（只部署 backend）
2. **决策 2**：MySQL/Milvus/MinIO 替换目标——我已经推荐了组合，也可以都换成云服务
3. **决策 3**：embedding 是否改 API

确认后我会：
- 把 `.env` 改成 PocketBay 友好的环境变量
- 写根级 `lumos/Dockerfile`
- 在 main.py 加 PocketBay 启动分支
- 生成 PocketBay 排除清单（已完成）

**Bash 工具恢复后我就能执行打包上传步骤**。当前会话已把不依赖 bash 的部分全部准备好了。