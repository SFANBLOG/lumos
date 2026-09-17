# ✨ 契光鉴微 —— 技术设计方案

> 版本：v0.4.0
> 日期：2026-03-09
> 状态：架构调整 (Flutter 客户端 + Python AI 服务端)
> 设计原则：**端侧顺滑体验、强悍的 AI Agent 大脑、数据隐私优先**

> ℹ️ 说明：本文档第 1–6 章为**项目早期架构设计基线**，部分技术选型与目录结构在落地时有所调整。
> 落地后的实际实现请以**附录 A（v0.6.0）**、**附录 B（v0.7.0）**及仓库代码为准；
> 各模块说明见 `backend/README.md`、`front/README.md`，归档客户端见 `archive/client/`。
> 二者冲突时，以附录与代码为准。

---

## 1. 为什么采用「Flutter 前端 + Python 后端」的双栈工作流？

在反复推演打工人的实际使用场景后，我们确立了系统的终极形态：**一个需要具备"复杂法律分析思考"能力的强大 Agent。** 

因此我们选择了**最优解组合**：
1. **APP 客户端 (Flutter)**：负责颜值、动画、跨平台、拍照、以及第一层**端侧 OCR 脱敏**（极度重要，保证用户真实隐私不上传）。
2. **AI 后端引擎 (Python + FastAPI)**：负责深度的 AI Agent 思考链路。因为排查合同不是简单的一问一答，而是复杂的流式分析（提取信息 -> 检索劳动法条款库 (RAG) -> 多轮论证 -> 得出严谨的谈判话术）。这个场景下，Python 生态（LangGraph, PydanticAI）的工程化能力碾压其他语言。

---

## 2. 核心技术栈

### 2.1 客户端 (Client-Side) - 极致感官篇
| 层 | 库/方案 | 作用与优势 |
|--------|--------|------------|
| **UI 框架** | **Flutter 3.x (Dart)** | Impeller 引擎提供丝滑的扫描光效动画。 |
| **状态/路由**| **Riverpod + go_router**| 类型安全的状态管理与深度链接。 |
| **硬件能力** | **camera + mlkit** | 调取镜头，利用 ML Kit 实现强大的全本地 OCR。 |
| **网络请求** | **Dio** | 与 Python 后端进行 HTTP/SSE (Server-Sent Events) 流式通信。 |
| **本地缓存** | **sqflite** | 离线缓存历史审查记录。 |

### 2.2 服务端 (Server-Side) - 智能大脑篇
| 层 | 库/方案 | 作用与优势 |
|--------|--------|------------|
| **基础框架** | **FastAPI (Python 3.11+)**| 速度极快，自带 Swagger 文档，与 Pydantic 完美契合。 |
| **AI 编排** | **LangGraph / PydanticAI** | 支持构建循环节点（Cyclic Graphs），让模型"懂思考、会改错"。 |
| **模型对接** | **LangChain / OpenAI SDK** | 无缝支持 DeepSeek、Claude、通义千问等兼容性接口。 |
| **文档进阶** | **LlamaIndex** | 用于复杂 PDF/Word 版式的提取与知识图谱构建。 |
| **数据库** | **SQLModel (SQLite/PG)** | FastAPI 原生作者开发的 ORM，无缝对接。 |

---

## 3. 系统架构设计

系统设计为云管端（Cloud/Client）架构：

```text
┌────────────────────────────────────────────────────────┐
│               Lumos Client (Flutter APP)               │
│                                                        │
│  [UI 表现层] 扫描合同 -> 播放极光动画 -> 展示风险卡片       │
│                                                        │
│  [端侧前置层] camera -> mlkit (OCR) -> 脱密正则替换       │
│                                                        │
│  [通信层] Dio Streaming (SSE接收分析过程)                │
└──────────────────────────┬─────────────────────────────┘
                           │ (脱敏后的合同纯文本)
                           ▼
┌────────────────────────────────────────────────────────┐
│               Lumos Server (Python AI Agent)           │
│                                                        │
│  [API 网关] FastAPI Endpoints                          │
│                                                        │
│  [Agent 思考引擎 (LangGraph / PydanticAI)]               │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1. 结构化抽取 Node: 将乱序文本抽取为标准字段表单        │  │
│  │ 2. 法规检索 Node (RAG): 根据提取的关键点查询判例库      │  │
│  │ 3. 风险审查 Node: 多维度打分并生成谈判话术            │  │
│  │ 4. 输出格式化 Node: 严格转为 JSON Stream 吐出前端      │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  [数据持久化] SQLModel (User Contracts / Chat History)   │
└────────────────────────────────────────────────────────┘
```

---

## 4. 核心工作流大解剖

### 步骤一：端侧智能脱敏 (Flutter 端)
APP 调用摄像头连续排下合同 1-10 页。`google_mlkit` 在**手机本地（完全不消耗网络）**识别出文字。
在把文本发给 Python 后端前，Flutter 端执行前置函数：
`TextCleaner.maskSensitive(text)` -> 将所有身份信息、银行卡、疑似私人公章抹除。

### 步骤二：流式上传与 Agent 启动 (Python 端)
FastAPI 接收到脱敏文本，触发 LangGraph 的工作流起点。
**之所以选 LangGraph，是因为合同审核必须严谨，一步不能错：**
- **Node A (纠错与对齐)**：大模型把 OCR 可能识别错的错别字修正，组合成结构化条款。
- **Node B (RAG 法规对照)**：大模型发现"试用期薪资 70%"，立刻挂起，去后台的向量数据库查询《劳动合同法》，确认为违法。
- **Node C (话术生成)**：基于上述结论，自动生成给 HR 的建议话术。

### 步骤三：SSE 流式响应与动画呈现 (双端配合)
Python 后端使用 Server-Sent Events (SSE) 将 Agent 思考的进度、风险的级别一点点推给前端。
Flutter 前端利用接收到的流，配合 `AnimationController`，在屏幕上挨个点亮红黄绿灯，给用户呈现极具科技感的"排雷"过程。

---

## 5. 目录结构规划

我们采用 Monorepo 思想，将前后端放于同一仓库：

```
lumos/
├── README.md
├── docs/                   # 文档
├── backend/                # Python 服务端
│   ├── app/
│   │   ├── api/            # FastAPI 路由 Controllers
│   │   ├── agent/          # LangGraph 核心智能体链
│   │   │   ├── nodes/      # 拆分的单步逻辑
│   │   │   └── tools/      # RAG 检索等自定义大模型工具
│   │   ├── core/           # 设置与 DB 连接
│   │   └── models/         # SQLModel 数据校验
│   ├── pyproject.toml      # Poetry / uv
│   └── Dockerfile
│
└── client/                 # Flutter 客户端
    ├── android/
    ├── ios/
    ├── lib/
    │   ├── core/           # 主题、路由、API Client
    │   ├── features/       # 业务模块 (scanner, report)
    │   └── shared/         # Widget 库
    └── pubspec.yaml
```

---

## 6. 后续规划

- **部署极简性**：后端使用现代化的 `uv` 搭配 Docker，一行代码 `docker-compose up` 就能在服务器启动专属的 AI 大脑。
- **本地降级方案**：未来可通过让 Python 节点直接调用本地的 Ollama，实现彻底的本地私海域审查。

---

## 附录 A：实现现状对照（v0.6.0 · 2026-09-08）

> 本文档第 1-6 章为早期设计基线；下表是落地后的实际实现，二者冲突处以本附录与仓库代码为准。

### A.1 技术选型落地情况

| 设计基线（早期） | 实际落地 | 说明 |
|---|---|---|
| LangGraph / PydanticAI 二选一 | **LangGraph 1.x 真 StateGraph** | `app/agent/graph.py`：extract → retrieve → review → negotiate 四节点线性链，节点共享 Pydantic `AgentState`（含 `events` 事件通道），`graph.astream` 增量回放事件；节点错误转 `THINKING` 警告并继续，全图失败才发 `ERROR` |
| 自研编排器 | 已废弃 | 早期 `supervisor.py` 手动 for 循环编排已删除，全部迁移至 LangGraph |
| SQLModel（SQLite/PG） | **SQLModel + aiomysql，MySQL 8** | Docker Compose 编排，宿主端口 3308 |
| 纯向量语义检索 | **向量 + BM25 混合检索（RRF 融合）** | `app/rag/`：向量通道（Milvus，不可用时直接关闭、仅剩 BM25）+ BM25 通道（jieba 分词 + 法律领域词典，零分未命中文档不进候选）→ `hybrid.py` RRF（k=60）融合排序；相关度分数 = 向量余弦与 BM25 归一分加权（单通道命中打折），任一通道失败自动降级单通道 |
| 向量库索引 | 未定型 | 现为：语料内容哈希 + embedding 签名双重校验，变化即自动重建；Milvus 集合名带签名后缀隔离；向量维度由模型自动探测，度量 COSINE |
| 文档解析（LlamaIndex） | 未采用 | 实际为轻量自有解析栈：pypdf / python-docx / openpyxl / python-pptx / RTF·HTML 纯标准库，支持 16 种扩展名 |
| OCR | 未定型 | 多模态视觉 LLM（通义千问 VL）+ Tesseract 本地兜底，`auto/llm/tesseract` 三级策略 |
| 模型接入 | 未定型 | LangChain ChatOpenAI 兼容层（DeepSeek 默认）；**RAG embedding 为真实模型双 Provider**：本地 sentence-transformers（默认 `BAAI/bge-base-zh-v1.5`）/ OpenAI 兼容 API，二者向量空间不一致时按签名自动重建索引 |
| 评测 | 未规划 | 已新增 `backend/eval/` 离线检索评测与测试体系，见 A.3 |

### A.2 目录结构对照

落地后 `backend/` 结构（与第 5 章规划相比）：

```
backend/
├── app/
│   ├── agent/               # LangGraph 编排
│   │   ├── graph.py         # StateGraph + SSE runner（取代 supervisor.py）
│   │   ├── state.py         # AgentState
│   │   ├── base.py / llm.py # 子智能体基类 / LLM 工厂
│   │   └── sub_agents/      # extractor/retriever/reviewer/negotiator/consultant
│   ├── rag/                 # 混合检索
│   │   ├── embeddings.py    # 双 Provider 真实 embedding
│   │   ├── milvus_store.py  # Milvus（COSINE/动态维度/签名隔离）
│   │   ├── vector_store.py  # search_laws 混合入口（向量 + BM25 → RRF）
│   │   ├── bm25_index.py    # BM25（jieba + 领域词典）
│   │   ├── hybrid.py        # RRF 融合
│   │   └── law_corpus.py    # 法条语料 + 哈希
│   ├── api/ core/ mcp/ models/ schemas/ services/ skills/
├── eval/                    # 检索评测 retrieval_eval.py（hit@k/MRR）
└── tests/                   # pytest（API 冒烟 + 检索 + 工作流 + e2e marker）
```

其余前端 `front/`、归档 `archive/client/`、部署 `docker-compose.yml` 与基线一致。

### A.3 测试与效果评测

- **单元/冒烟测试**：27 条 pytest 用例（默认跑 25：API 冒烟、BM25/领域词典、RRF 融合、Milvus 失败降级、LangGraph 状态流转与错误恢复；另 2 条 e2e 需 `LUMOS_E2E=1`）；`pytest --cov=app` 输出行覆盖率（RAG 核心模块 70%+，Milvus 依赖真实服务的分支由 e2e 覆盖）。
- **离线检索评测**：以 `data/contracts/` 90 份单分类金标准（高危/警惕/关注三区 × 9 类 × 10 份）抽取风险句为查询，分向量 / BM25 / 混合三通道统计 `hit@1/3/5` 与 `MRR@5`，输出 `backend/eval/output/retrieval_eval_latest.{md,json}`。
- **量化口径边界**：`backend/app` 行数、语料份数、用例条数均为**开发规模指标**；检出率 / `hit@k` / `MRR` 等**效果指标**一律以评测脚本输出为准（见根 README §八），二者不可混用表述。

---

## 附录 B：实现现状对照（v0.7.0 · 2026-09-10）

> 本附录记录相对附录 A（v0.6.0）的增量落地情况，聚焦**工程健壮性、可运维性与运行环境**。

### B.1 增量变更

| 主题 | 变更前 | 现状（v0.7.0） | 涉及文件 |
|---|---|---|---|
| Milvus 接入方式 | ORM-style `Collection.*`（`insert` / `flush` / `num_entities` / `search`），触发 `PyMilvusDeprecationWarning` | **`MilvusClient` 客户端 API**：`create_schema` → `prepare_index_params` → `create_collection` → `insert`（行式 dict）→ `search` / `query` / `get_collection_stats`，兼容 PyMilvus 3.1+ | `app/rag/milvus_store.py` |
| 日志落盘 | 仅 `APP_ENV=production` 写文件，且路径相对 CWD | **开发/生产均落盘** `backend/logs/lumos_<日期>.log`：每日零点轮转、保留 30 天、gz 压缩、UTF-8、`enqueue=True`（退出时 atexit 刷盘）、路径以 `BASE_DIR` 锚定不依赖 CWD | `app/core/logging.py` |
| SQL 回显 | `echo=settings.is_development`（开发环境必然回显，控制台被 `SELECT` 刷屏） | 新增配置 **`DATABASE_ECHO`（默认 false）**；并在日志初始化时把标准库 `sqlalchemy` / `sqlalchemy.engine` / `pool` / `dialects` 收敛至 **WARNING**，显式开启回显时才放开到 INFO | `app/core/config.py`、`app/core/database.py`、`app/core/logging.py` |
| Python 版本 | 声明 3.12（与实际运行时不符，IDE 报 `from __future__ import annotations` 冗余） | 对齐 **3.11**：`requires-python` / ruff `target-version` / mypy `python_version` 三处统一 | `pyproject.toml` |
| embedding 路径解析 | 直接把配置值交给 `SentenceTransformer`，非 `backend/` CWD 下解析失败，且触发对 `modules.json` / `adapter_config.json` 的 HF HEAD 探测（国内超时 `WinError 10060`） | 新增 `_resolve_local_model()`：取 basename 到 `backend/models/` 查找，命中即强制 `local_files_only=True`，**完全跳过 HF 探测**；未命中才走 `HF_ENDPOINT` 镜像下载 | `app/rag/embeddings.py` |
| 构建/版本控制 | 构建上下文包含运行日志；模型权重、日志未完全排除 | `.dockerignore` 排除 `logs/`；`.gitignore` 覆盖 `backend/models/`、`backend/logs/` | `.dockerignore`、`.gitignore` |

### B.2 目录增量

```
backend/
├── app/core/logging.py     # loguru 控制台 + 文件双 sink；收敛 sqlalchemy 标准库日志器
├── logs/                   # 运行日志 (每日轮转, gitignore)
├── models/bge-base-zh-v1.5/# 本地 embedding 权重 (扁平命名, gitignore)
└── pyproject.toml          # requires-python >=3.11
```

### B.3 约定（新增，务必遵守）

1. **模型目录约定**：本地 embedding 权重统一为**扁平命名** `backend/models/<model-dir>/`，不再使用 `models/<org>/<model-dir>/` 或 HF hub-cache 式 `snapshots/` 结构；配置里写 `bge-base-zh-v1.5`、`models/bge-base-zh-v1.5`、`BAAI/bge-base-zh-v1.5` 均可被解析到同一目录。
2. **日志约定**：应用日志走 loguru；第三方库（SQLAlchemy 等）走标准库 logging，需在 `setup_logging()` 内统一收敛级别，避免绕过 loguru 直打控制台。
3. **CWD 无关**：所有运行时路径（日志目录、模型目录）必须以 `BASE_DIR`（= `backend/`）锚定，保证从仓库根或 `backend/` 启动行为一致。
4. **调试 SQL**：仅在需要时置 `DATABASE_ECHO=true`，不要为调试长期打开（会污染日志文件并拖慢 I/O）。

### B.4 排障速查

| 现象 | 根因 | 处置 |
|---|---|---|
| `FileNotFoundError: Path models/... not found` | 配置路径与磁盘目录不一致（含/不含 org 前缀） | 核对 `backend/models/` 实际目录名，按 B.3 约定书写 |
| 启动日志刷 `INFO sqlalchemy.engine.Engine SELECT ...` | `DATABASE_ECHO=true` 或旧代码 `echo=is_development` | 置 `DATABASE_ECHO=false` 并重启；确认 `setup_logging()` 已收敛日志器 |
| `WinError 10060` 请求 `huggingface.co/.../modules.json` | 本地权重未被识别，sentence-transformers 走 HF 探测 | 确认本地权重目录存在且命名符合 B.3；必要时设 `HF_ENDPOINT=https://hf-mirror.com` |
| `PyMilvusDeprecationWarning: Collection.xxx will be removed` | 仍在使用 ORM-style API | 使用 `MilvusClient` 客户端 API（见 B.1） |
| 前端请求后端 404 | 8000 端口被其他服务（如 Milvus Attu）占用，或 Vite 代理未指到后端实际端口 | 确认后端实际端口（默认 `8001`）；确认 `vite.config.ts` 中 `/api → localhost:8001`；排查时加 `--noproxy '*'` |
