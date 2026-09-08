# 🔍 Lumos · 契光鉴微

**开源 AI 合同风险排查助手** — 拍照即查，深度适配中国劳动法，完全免费，为每一位劳动者而设计。

---

## 目录

- [一、项目背景](#一项目背景)
- [二、功能特性](#二功能特性)
- [三、界面预览](#三界面预览)
- [四、技术栈](#四技术栈)
- [五、系统架构](#五系统架构)
- [六、Agent 与 MCP 架构](#六agent-与-mcp-架构)
- [七、快速开始（Docker / 本地）](#七快速开始docker--本地)
- [八、环境变量](#八环境变量)
- [九、API 一览](#九api-一览)
- [十、项目结构](#十项目结构)
- [十一、参与贡献](#十一参与贡献)
- [十二、免责声明与许可证](#十二免责声明与许可证)

---

## 一、项目背景

> *"签了个合同，后来才发现有竞业禁止条款，离职后两年不能去同行，违约金还要赔 50 万。"*

每年有超过 **1200 万人** 进入中国就业市场。他们中的大多数人——尤其是应届毕业生和初入职场的年轻人——在签劳动合同时面临一个共同的困境：

| 痛点 | 现状 |
| :--- | :--- |
| 💰 **费用高昂** | 审阅一份合同通常收费 500–2000 元，应届生根本负担不起 |
| 📜 **看不懂** | 晦涩的法律术语，不知道哪些条款暗藏玄机 |
| 😶 **不敢问** | 迫于入职压力，不敢对 HR 提供的格式合同提出质疑 |

现有的 AI 合同审查工具几乎全部是为**企业法务和律师**设计的。**Lumos · 契光鉴微** 就是要填补这个空白——它是**第一个完全免费、开源、站在劳动者视角的 AI 合同风险排查助手**。

> 💡 *用光，照见契约中每一个隐形陷阱。*

---

## 二、功能特性

| 能力 | 说明 |
|---|---|
| **十大坑点智能检测** | 深度适配中国劳动法，自动扫描竞业禁止、试用期不缴社保、变相扣薪、含糊岗位职责、苛刻离职审批等 **10 类风险条款** |
| **拍照即查** | 纸质合同拍照上传，端侧 OCR + 服务端多模态 LLM 双重文字抽取，PDF/Word 同样支持 |
| **「说人话」的条款解读** | AI 将晦涩法律术语翻译成「大白话」，并附上具体法律依据，告诉你"这条到底是什么意思" |
| **一键生成谈判话术** | 不只告诉你坑在哪，还生成可直接复制、通过微信发送的专业话术，有理有据，不卑不亢 |
| **Multi-Agent 分析引擎** | Extract → Retrieve → Review → Negotiate 四阶段流水线，每个阶段由独立子智能体专精处理 |
| **RAG 法规检索** | 基于 Milvus 向量数据库 + 混合检索的中国劳动法条文语义检索，答案可溯源到具体法条 |
| **SSE 流式实时推送** | 分析全过程以 SSE 事件流实时推送，前端展示思考过程时间线，体验透明可信 |
| **智能咨询** | 独立于合同分析的智能问答模块，支持法律问题自由咨询，关联已分析合同风险上下文 |
| **MCP 协议支持** | 内置 MCP Server，将法条检索、条款分析、风险评分、谈判话术等能力标准化暴露，方便二次开发与外部 Agent 集成 |
| **多端覆盖** | Flutter 移动端（iOS/Android）+ Vue 3 Web 端，同一后端服务，全场景触达 |

---

## 三、界面预览

| 平台 | 功能截图 |
|:---|:---|
| Web 工作台 | 分析看板、合同列表、风险概览统计 |
| Web 合同分析 | 极光动画等待 → 风险卡片逐条呈现 → 完整报告 |
| Web 智能咨询 | 多轮对话，法条引用标注，追问建议 |
| Web MCP 工具箱 | MCP 工具列表与调用 |

> 完整截图见 `web/shots/` 目录。

---

## 四、技术栈

**客户端（Flutter）**

| 技术 | 说明 |
|:---|:---|
| Flutter 3.x (Dart) | Impeller 引擎，丝滑扫描光效动画 |
| Riverpod (代码生成, 自动缓存) | 类型安全的状态管理 |
| go_router | 深度链接与路由 |
| Dio (SSE) | 流式实时接收 AI 分析过程 |

**Web 端（Vue 3）**

| 技术 | 说明 |
|:---|:---|
| Vue 3 + TypeScript | 组件化、类型安全的现代化前端 |
| Vite | 极速构建工具 |
| Pinia | 状态管理 |
| Element Plus | UI 组件库 |
| Axios (SSE) | 流式请求与 REST 通信 |

**服务端（Python FastAPI）**

| 技术 | 说明 |
|:---|:---|
| FastAPI (Python 3.12) | 极速异步框架 + 自动 Swagger 文档 |
| LangGraph | 子智能体编排与状态流转 |
| Supervisor + 4 子智能体 | 编排器架构：Extractor → Retriever → Reviewer → Negotiator |
| LangChain / OpenAI SDK | 任意 OpenAI 兼容接口（DeepSeek / Claude / 通义千问等） |
| SQLModel + aiomysql | 异步 ORM，MySQL 持久化 |
| Milvus | 向量数据库，劳动法条文语义检索 |
| ChromaDB | 轻量向量检索降级方案 |
| MinIO | 对象存储，合同文件与扫描件上传 |

---

## 五、系统架构

系统采用**前后端分离**的现代 Agent 架构，结合移动端原生性能、Web 端便捷性与后端强大的 AI 编排能力。

```
┌───────────────────────────────────────────────────────────┐
│              📱 Lumos Client (Flutter APP)                │
│              💻 Lumos Web (Vue 3 + Vite)                  │
│                                                           │
│   [UI 表现层]  扫描合同 → 播放极光动画 → 展示风险卡片       │
│   [通信层]     Dio / Axios Streaming (SSE 接收分析过程)     │
└────────────────────────┬──────────────────────────────────┘
                         │  📤 脱敏后的合同纯文本
                         ▼
┌───────────────────────────────────────────────────────────┐
│              🧠 Lumos Server (Python AI Agent)            │
│                                                           │
│   [API 网关]  FastAPI Endpoints                           │
│   [认证授权]  JWT + API Key                               │
│   [Agent 引擎] Supervisor + 4 子智能体                    │
│     ├── 1. Extractor   — 结构化抽取：乱序文本 → 标准条款   │
│     ├── 2. Retriever   — 法规检索 (RAG)：Key条款 → 法条    │
│     ├── 3. Reviewer    — 风险审查：多维度打分 + 法律依据    │
│     └── 4. Negotiator  — 谈判策略：为每条风险生成话术      │
│   [数据持久化] SQLModel + MySQL 8                          │
│   [对象存储]   MinIO (PDF/Word/图片上传)                   │
│   [向量检索]   Milvus (劳动法条文语义检索)                 │
└───────────────────────────────────────────────────────────┘
```

### 5.1 一次合同分析的完整链路

```
用户提交合同文本
 │
 ├─ [Extractor] 文本清洗（OCR 纠错/段落规范化）
 │   └─ 调用 LLM 将合同拆分为结构化条款（含风险预分类）
 │   └─ LLM 失败时降级为段落分割
 │
 ├─ [Retriever] 对每条已提取条款，通过 MCP law_search 工具
 │   └─ 进行 RAG 语义检索（Milvus 向量 + BM25 混合）
 │   └─ 去重后排序，填充 legal_references
 │
 ├─ [Reviewer] 构建条款+法条上下文
 │   └─ 调用 LLM 逐项评估风险（评分/等级/法律依据/谈判话术）
 │   └─ LLM 失败时降级为规则审查
 │
 ├─ [Negotiator] 对缺失 negotiation_tip 的条目
 │   └─ 通过 MCP negotiation 工具填充谈判话术
 │
 └─ [格式化输出] SSE 事件流 → 前端风险卡片展示
```

---

## 六、Agent 与 MCP 架构

### 6.1 Supervisor + 4 个子智能体

```
SupervisorAgent（编排器，不继承 BaseAgent）
 │
 ├─ 🔧 ExtractorAgent  — 文本抽取/OCR纠错/条款结构化
 │   └─ skills: text_preprocessing
 │
 ├─ 📚 RetrieverAgent  — 法规检索（RAG）
 │   └─ MCP 工具: law_search
 │
 ├─ ⚖️ ReviewerAgent   — 风险审查/评分
 │   └─ skills: legal_analysis, risk_scoring
 │   └─ MCP 工具: risk_assess, clause_analyze
 │
 └─ 💬 NegotiatorAgent — 谈判策略生成
     └─ MCP 工具: negotiation
```

| 子智能体 | key | 擅长场景 |
|---|---|---|
| ExtractorAgent | `extractor` | 合同文本清洗、OCR 纠错、条款结构化拆分 |
| RetrieverAgent | `retriever` | 劳动法条文语义检索、RAG 召回 |
| ReviewerAgent | `reviewer` | 风险多维度打分、法律依据生成、谈判话术 |
| NegotiatorAgent | `negotiator` | 补充谈判话术，确保每条风险都有应对策略 |

**额外独立智能体：**

| 智能体 | key | 用途 |
|---|---|---|
| ConsultantAgent | `consultant` | 独立于合同分析流的智能咨询模块，支持多轮对话、法条引用、追问建议 |

### 6.2 技能系统（Skills）

技能是**多步骤、可复用**的能力单元，由注册表统一管理：

| 技能 | key | 用途 |
|---|---|---|
| 文本预处理 | `text_preprocessing` | OCR 文本清洗、段落规范化 |
| 法律分析 | `legal_analysis` | 条款合法性评估 |
| 风险评分 | `risk_scoring` | 风险等级与分值量化 |
| 谈判策略 | `negotiation` | 谈判话术生成 |
| 追问建议 | `followup_suggestion` | 智能咨询追问推荐 |

### 6.3 MCP 工具（4 个）

| 工具 | 说明 | 数据来源 |
|---|---|---|
| `law_search` | 检索劳动法条文知识库，返回带相关度的片段 | `rag/retriever.py` 混合检索（Milvus + BM25） |
| `risk_assess` | 对结构化条款进行风险评分与法律依据匹配 | ReviewerAgent 内部逻辑 |
| `clause_analyze` | 对单一条款进行深度分析 | LLM + 法条上下文 |
| `negotiation` | 为风险条款生成可执行谈判话术 | LLM 生成 |

### 6.4 MCP（Model Context Protocol）

内置 **MCP Server**（FastAPI 路由，JSON-RPC 2.0 over HTTP，端点 `/api/v1/mcp`）：

| 方法 | 说明 |
|---|---|
| `tools/list` | 暴露全部 4 个工具的标准 schema |
| `tools/call` | 桥接执行 MCP 工具 |
| `resources/list` / `resources/read` | 把知识库文档暴露为可读资源 |

配套 `backend/app/mcp/client.py`（MCP Client）可连接任意外部 MCP 服务。

### 6.5 SSE 事件协议

| 事件 | 载荷 | 说明 |
|---|---|---|
| `NODE_START` | `{node_name, description, progress}` | 子智能体开始执行 |
| `NODE_COMPLETE` | `{node_name, description, progress}` | 子智能体执行完成 |
| `THINKING` | `{content}` | 节点出错时推送警告 |
| `RISK_FOUND` | `{category, level, title, explanation, ...}` | 逐条推送风险评估结果 |
| `SUMMARY` | `{overall_score, overall_level, summary, ...}` | 分析完成推送总计 |
| `COMPLETE` | — | 流程结束 |

---

## 七、快速开始（Docker / 本地）

### 前置要求

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/)
- [Node.js](https://nodejs.org/) 18+（Web 端开发）
- [Flutter](https://flutter.dev/docs/get-started/install) 3.x+（移动端开发，可选）
- [Python](https://www.python.org/) 3.12+（服务端开发，可选）

### 7.1 方式一：Docker Compose 一键部署（推荐）

```bash
# 1. 准备环境变量（按需修改 LLM_API_KEY 等）
cp .env.example .env

# 2. 构建并后台启动
docker compose up -d --build

# 3. 查看状态与日志
docker compose ps
docker compose logs -f backend
```

**服务清单（7 个容器）**

| 服务 | 镜像 | 端口（宿主机 → 容器） | 用途 |
|---|---|---|---|
| `mysql` | mysql:8.0 | 3308 → 3306 | 业务数据库 |
| `minio` | minio/minio:latest | 9000 / 9001 | 对象存储 |
| `milvus-etcd` | quay.io/coreos/etcd:v3.5.5 | — | Milvus 元数据 |
| `milvus-minio` | minio/minio:latest | — | Milvus 对象存储 |
| `milvus-standalone` | milvusdb/milvus:v2.4.0 | 19530 | 向量数据库 |
| `backend` | 本地构建 | 8001 → 8000 | FastAPI AI 服务端 |
| `web` | 本地构建 | 8080 → 80 | Nginx 托管 Web 前端 |

**访问地址**

| 入口 | 地址 |
|---|---|
| Web 前端 | [http://localhost:8080](http://localhost:8080) |
| API 文档（Swagger） | [http://localhost:8001/docs](http://localhost:8001/docs) |
| MinIO 管理台 | [http://localhost:9001](http://localhost:9001) |

### 7.2 方式二：本地独立部署

**后端：**

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# 编辑 .env 填入 AI API Key 等配置
uvicorn app.main:app --reload
```

**Web 前端：**

```bash
cd web
npm install
npm run dev
```

**Flutter 客户端：**

```bash
cd client
flutter pub get
flutter run
```

---

## 八、环境变量

| 分组 | 变量 | 默认值 | 说明 |
|---|---|---|---|
| 应用 | `APP_ENV` | `development` | 运行环境 |
| | `LOG_LEVEL` | `DEBUG` | 日志级别 |
| 数据库 | `DATABASE_URL` | `mysql+aiomysql://lumos:lumos@localhost:3306/lumos` | MySQL 连接串 |
| | `MYSQL_ROOT_PASSWORD` | `root` | MySQL root 密码 |
| LLM | `LLM_API_KEY` | （必填） | AI 模型 API Key |
| | `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容接口地址 |
| | `LLM_MODEL_NAME` | `deepseek-chat` | 模型名称 |
| 安全 | `JWT_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Token 过期时间（7 天） |
| Milvus | `MILVUS_HOST` | `localhost` | 向量数据库地址 |
| | `MILVUS_PORT` | `19530` | 向量数据库端口 |
| | `MILVUS_COLLECTION` | `labor_laws` | 集合名称 |
| MinIO | `MINIO_ENDPOINT` | `localhost:9000` | 对象存储地址 |
| | `MINIO_ACCESS_KEY` | `minioadmin` | 访问密钥 |
| | `MINIO_SECRET_KEY` | `minioadmin` | 秘密密钥 |
| | `MINIO_BUCKET` | `lumos` | 存储桶名称 |

---

## 九、API 一览

| 模块 | 方法 | 端点 | 描述 |
|:---|:---|:---|:---|
| 健康检查 | `GET` | `/api/v1/health` | 服务健康检查 |
| | `GET` | `/api/v1/health/ready` | 就绪检查（依赖可用性） |
| 认证 | `POST` | `/api/v1/auth/register` | 用户注册 |
| | `POST` | `/api/v1/auth/login` | 用户登录（返回 JWT） |
| | `GET` | `/api/v1/auth/me` | 当前用户信息 |
| 合同分析 | `GET` | `/api/v1/contracts` | 合同记录列表（分页） |
| | `GET` | `/api/v1/contracts/stats` | 看板统计汇总 |
| | `POST` | `/api/v1/contracts` | 提交合同分析 |
| | `GET` | `/api/v1/contracts/{id}/stream` | SSE 流式分析过程 |
| | `GET` | `/api/v1/contracts/{id}/report` | 获取完整报告 |
| | `GET` | `/api/v1/contracts/{id}` | 查询单个合同记录 |
| MCP 工具 | `GET` | `/api/v1/mcp/tools` | 列出 MCP 工具（含 schema） |
| | `POST` | `/api/v1/mcp/tools/call` | 调用 MCP 工具 |
| 智能导入 | `POST` | `/api/v1/ingest/file` | 上传文件抽取文本（10 种格式 + OCR） |
| | `POST` | `/api/v1/ingest/url` | 抓取网页抽取正文 |
| 智能咨询 | `POST` | `/api/v1/consult/ask` | 发起智能咨询（SSE 流式） |
| | `GET` | `/api/v1/consult/sessions` | 会话列表 |
| | `GET` | `/api/v1/consult/sessions/{id}/messages` | 会话消息记录 |
| | `DELETE` | `/api/v1/consult/sessions/{id}` | 删除会话 |

> 完整 OpenAPI 文档在本地启动后端后访问 `http://localhost:8001/docs`。

---

## 十、项目结构

```
lumos/
├── README.md                          # 项目说明
├── docker-compose.yml                 # 一键部署（MySQL/MinIO/Milvus/后端/Web）
├── .env.example                       # 环境变量模板
├── .gitignore
│
├── client/                            # Flutter 移动端（iOS/Android）
│   └── lib/
│       ├── core/                      # API、状态、路由、主题
│       ├── features/                  # 业务功能模块（analysis/home/main/mcp/report/scanner/splash）
│       └── shared/                    # 公共组件
│
├── web/                               # Vue 3 Web 前端
│   ├── src/
│   │   ├── api/                       # API 接口封装（auth/client/contract/consult/ingest）
│   │   ├── layouts/                   # 布局组件
│   │   ├── router/                    # 路由与登录守卫
│   │   ├── stores/                    # Pinia 状态管理
│   │   ├── utils/                     # 通用工具
│   │   ├── views/                     # 页面（Dashboard/Analysis/Reports/Consult/MCP/Login/Register）
│   │   ├── App.vue
│   │   └── main.ts
│   └── Dockerfile + nginx.conf
│
├── backend/                           # Python FastAPI 服务端
│   ├── app/
│   │   ├── agent/                     # Multi-Agent 编排
│   │   │   ├── base.py               # 子智能体抽象基类 BaseAgent
│   │   │   ├── supervisor.py         # 编排器 SupervisorAgent
│   │   │   ├── graph.py              # 工作流入口 run_contract_analysis()
│   │   │   ├── state.py              # LangGraph AgentState
│   │   │   ├── llm.py                # LLM 客户端工厂（ChatOpenAI / Vision）
│   │   │   └── sub_agents/           # 子智能体（Extractor/Retriever/Reviewer/Negotiator/Consultant）
│   │   ├── api/v1/                   # FastAPI 路由
│   │   ├── core/                      # 配置、数据库、安全、MinIO
│   │   ├── mcp/                      # MCP 协议（Server/Client/Tools）
│   │   ├── models/                   # 数据模型（SQLModel）
│   │   ├── rag/                      # 向量检索（Milvus/ChromaDB/BM25）
│   │   └── skills/                   # 可复用技能
│   ├── tests/                        # 测试
│   └── pyproject.toml
│
├── docs/                              # 项目文档
│   └── technical-design.md           # 技术设计方案
│
├── data/                              # 测试数据（100 份中文合同样本）
│
└── public/                            # 静态资源
```

---

## 十一、参与贡献

Lumos 是一个为劳动者发声的公益开源项目，我们需要多元化的力量：

- ⚖️ **法律从业者** — 完善判例库、优化风险检测规则
- 💻 **开发者** — 提交 PR，优化系统性能与 UI 细节
- 🧑 **每一个打工人** — 分享你踩过的坑，让 AI 学习并保护更多人

欢迎提交 Issue 或 Pull Request！详见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

## 十二、免责声明与许可证

### 免责声明

**Lumos · 契光鉴微** 是一款基于人工智能的辅助审阅工具。系统检测结果与话术仅供参考，**不构成具有法定效力的专业法律建议**。对于标的额巨大或情况极其复杂的劳动争议，建议您线下咨询专业持证律师。

### 许可证

本项目基于 [Apache 2.0 License](./LICENSE) 开源。Copyright © 2026 Lumos Contributors.

---

<p align="center">
  <strong>✨ 照见契约中最细微的陷阱</strong>
</p>