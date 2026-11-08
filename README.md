# 🔍 契光鉴微

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
- [八、测试、评测与量化口径](#八测试评测与量化口径)
- [九、环境变量](#九环境变量)
- [十、API 一览](#十api-一览)
- [十一、项目结构](#十一项目结构)
- [十二、参与贡献](#十二参与贡献)
- [十三、免责声明与许可证](#十三免责声明与许可证)

---

## 一、项目背景

> *"签了个合同，后来才发现有竞业禁止条款，离职后两年不能去同行，违约金还要赔 50 万。"*

每年有超过 **1200 万人** 进入中国就业市场。他们中的大多数人——尤其是应届毕业生和初入职场的年轻人——在签劳动合同时面临一个共同的困境：

| 痛点 | 现状 |
| :--- | :--- |
| 💰 **费用高昂** | 审阅一份合同通常收费 500–2000 元，应届生根本负担不起 |
| 📜 **看不懂** | 晦涩的法律术语，不知道哪些条款暗藏玄机 |
| 😶 **不敢问** | 迫于入职压力，不敢对 HR 提供的格式合同提出质疑 |

现有的 AI 合同审查工具几乎全部是为**企业法务和律师**设计的。**契光鉴微** 就是要填补这个空白——它是**第一个完全免费、开源、站在劳动者视角的 AI 合同风险排查助手**。

> 💡 *用光，照见契约中每一个隐形陷阱。*

---

## 二、功能特性

| 能力 | 说明 |
|---|---|
| **十大坑点智能检测** | 深度适配中国劳动法，自动扫描竞业禁止、试用期不缴社保、变相扣薪、含糊岗位职责、苛刻离职审批等 **10 类风险条款** |
| **拍照即查** | 纸质合同拍照上传，端侧 OCR + 服务端多模态 LLM 双重文字抽取；PDF/Word 同样支持，**扫描版/混排版 PDF 逐页自动 OCR**（无文字层的页渲染位图后识别） |
| **MinerU 版面解析** | 复杂版面的合同 PDF 可选接入 **MinerU**（本机 `mineru-kit` / `mineru` CLI 或内网 HTTP 解析服务）做版面检测、阅读顺序还原、表格/公式识别与 OCR，输出 Markdown + `content_list` 结构化块；版面中切出的公章/签名/手写批注图片块再交给**多模态视觉大模型**补识并回填原位置。未安装 MinerU 时自动回退内置 pypdf + PyMuPDF + OCR 链路，`/ingest/file` 返回 `parse_meta` 说明本次解析引擎与回退原因（详见 §5.2） |
| **「说人话」的条款解读** | AI 将晦涩法律术语翻译成「大白话」，并附上具体法律依据，告诉你"这条到底是什么意思" |
| **一键生成谈判话术** | 不只告诉你坑在哪，还生成可直接复制、通过微信发送的专业话术，有理有据，不卑不亢 |
| **多智能体分析引擎** | 以 **LangGraph StateGraph** 编排 Coordinator → Extractor → Retriever → Reviewer → Verifier → Negotiator 六个自治智能体，通过消息总线协作；Verifier 可否决结论并触发条件返工，事件累积回放为 SSE 时间线（`AGENT_MODE=linear` 可回退旧四节点链路） |
| **混合检索 RAG** | **真实 embedding 模型**（默认本地 sentence-transformers，可切 API）向量化法条语料；检索 = **双路召回**（Milvus 向量 + BM25 jieba 分词）→ **RRF 融合** → **精排**（Reranker 重排 + 相似度阈值过滤），答案可溯源到具体法条；风险审查节点对 `legal_basis` 抽取「法名+条号」与召回法条逐条溯源核验，命中不了标注待人工复核并扣减置信度 |
| **SSE 流式实时推送** | 分析全过程以 SSE 事件流实时推送，前端展示思考过程时间线，体验透明可信 |
| **智能咨询** | 独立于合同分析的智能问答模块，支持法律问题自由咨询，关联已分析合同风险上下文 |
| **MCP 协议支持** | 内置 MCP Server，将法条检索、条款分析、风险评分、谈判话术等能力标准化暴露，方便二次开发与外部 Agent 集成 |
| **A2A 协议支持** | 内置 A2A（Agent2Agent Protocol）端点，对外暴露标准 Agent Card（`/.well-known/agent.json`）与 JSON-RPC 端点（`/a2a` 同步、`/a2a/stream` SSE 流式），可被任意 A2A 客户端/其他 Agent 发现并调用，实现 Agent 间对等协作 |
| **多端覆盖** | Vue 3 Web 端为主；Flutter 移动端已归档（未纳入本仓库），同一后端服务 |

---

## 三、界面预览

| 工作台 | 合同分析结果 | 智能咨询 |
|:---:|:---:|:---:|
| ![工作台](https://gitee.com/BLOGSFan/lumos/raw/main/front/shots/dashboard.png) | ![合同分析](https://gitee.com/BLOGSFan/lumos/raw/main/front/shots/analysis-result.png) | ![智能咨询](https://gitee.com/BLOGSFan/lumos/raw/main/front/shots/consult-3-answering.png) |

| 文件导入分析 | MCP 工具箱 | 报告详情 |
|:---:|:---:|:---:|
| ![文件分析](https://gitee.com/BLOGSFan/lumos/raw/main/front/shots/file-analysis-result.png) | ![MCP 工具](https://gitee.com/BLOGSFan/lumos/raw/main/front/shots/mcp-1-law-search.png) | ![报告抽屉](https://gitee.com/BLOGSFan/lumos/raw/main/front/shots/report-drawer.png) |

> 完整截图（含登录、咨询全流程、生产环境演练等 23 张）见 `front/shots/` 目录。

---

## 四、技术栈

**移动端（Flutter，已归档，未纳入本仓库）**

> ⚠️ 遗留 Flutter 移动端代码已归档，未纳入本仓库（原 `archive/client/`），仅供历史参考。

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
| FastAPI (Python 3.11+) | 极速异步框架 + 自动 Swagger 文档 |
| LangGraph 1.x | 真 `StateGraph` 多智能体图：coordinator → extract → retrieve → review → verifier → negotiate，含条件边与返工回边，共享 Pydantic `AgentState` 与 `agent_messages` 消息总线 |
| LangChain / OpenAI SDK | 任意 OpenAI 兼容接口（DeepSeek / Claude / 通义千问等） |
| SQLModel + aiomysql | 异步 ORM，MySQL 持久化 |
| 真实 Embedding | `sentence-transformers` 本地模型（默认 `BAAI/bge-base-zh-v1.5`，768 维中文检索，BGE query 指令优化）或 OpenAI 兼容 API 双 Provider；向量索引按「语料 + embedding 签名」自动隔离重建 |
| Milvus | 向量数据库（COSINE，动态维度）；不可用时向量通道自动关闭，仅保留 BM25 关键词检索 |
| BM25 (jieba) | 法条语料全文关键词通道（零分未命中文档不进候选），与向量通道经 **RRF** 融合；相关度分数 = 向量余弦与 BM25 归一分加权（单通道命中打折） |
| Reranker（精排） | RRF 融合候选再经 `rerank_candidates` 精排：默认轻量可解释精排（召回分 + 词覆盖 + 标题命中加权），可选 CrossEncoder（`BAAI/bge-reranker-base`）语义重排，并按相似度阈值过滤后取 Top-K |
| MinerU（可选） | 复杂版面 PDF → Markdown/JSON：`services/mineru_parser.py` 适配本机 CLI（4.x `mineru-kit parse` / 2.x `mineru -p`）与内网 HTTP 服务（`scripts/mineru_http_server.py`）；未安装自动回退内置链路，不影响服务启动 |
| 多模态视觉大模型 | 通义千问 VL（OpenAI 兼容）用于合同拍照/扫描件 OCR，以及 MinerU 版面图片块（公章/签名/手写批注）的语义补识；`auto` 策略失败回退本地 Tesseract |
| MinIO | 对象存储，合同文件与扫描件上传 |
| A2A（Agent2Agent Protocol） | 标准 Agent 协议集成层（`app/a2a`）：Agent Card 自描述 + JSON-RPC 2.0（`/a2a`）+ SSE 流式（`/a2a/stream`），复用 LangGraph 工作流对外提供能力 |

---

## 五、系统架构

系统采用**前后端分离**的现代 Agent 架构，结合移动端原生性能、Web 端便捷性与后端强大的 AI 编排能力。

```mermaid
flowchart TB
    subgraph L1["① 客户端层"]
        direction LR
        W["Vue 3 Web 端<br/>Vite · Pinia · Element Plus · Axios（SSE）"]
        M["Flutter 移动端（已归档）<br/>Riverpod · go_router · Dio（SSE）"]
    end

    subgraph L2["② API 网关层 · FastAPI"]
        direction LR
        A1["认证鉴权<br/>JWT + API-Key"]
        A2["中间件<br/>限流 · 日志 · 指标 · 全局异常"]
        A3["路由<br/>REST + SSE · 19 端点"]
    end

    subgraph L3["③ Agent 编排层 · LangGraph StateGraph"]
        direction LR
        N1["1 ExtractorAgent<br/>抽取 · OCR 纠错 · 条款结构化"]
        N2["2 RetrieverAgent<br/>混合检索召回法条"]
        N3["3 ReviewerAgent<br/>风险评级 · 评分 · 法条依据"]
        N4["4 NegotiatorAgent<br/>谈判话术生成"]
        N5["ConsultantAgent<br/>独立智能咨询"]
        N1 --> N2 --> N3 --> N4
    end

    subgraph L4["④ 检索链路 · Hybrid RAG"]
        direction LR
        E1["Embedding<br/>bge-base-zh-v1.5 · 768 维"]
        V1["Milvus 向量通道<br/>COSINE · 签名隔离集合"]
        B1["BM25 关键词通道<br/>jieba + 法律领域词典"]
        F1["RRF 融合<br/>k = 60"]
        R1["精排 Reranker<br/>可解释 / CrossEncoder"]
        E1 --> V1 --> F1
        B1 --> F1
        F1 --> R1
    end

    subgraph L5["⑤ 存储与协议"]
        direction LR
        S1["MySQL 8<br/>SQLModel · aiomysql"]
        S2["MinIO<br/>合同原件"]
        S3["MCP Server<br/>JSON-RPC 2.0 · 4 工具"]
        S4["A2A Server<br/>Agent Card · /a2a · 流式"]
    end

    L1 --> L2 --> L3
    N2 --> L4
    R1 --> N3
    L3 --> L5
```

### 5.1 一次合同分析的完整链路

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户 / 前端
    participant API as FastAPI 网关
    participant G as LangGraph 工作流
    participant R as 混合检索 RAG
    participant L as LLM

    U->>API: POST /api/v1/contracts 提交合同文本
    API->>G: 启动 StateGraph（共享 Pydantic AgentState）
    API-->>U: 返回 contract_id

    U->>API: GET /contracts/id/stream（SSE 订阅）
    G-->>U: NODE_START extractor
    G->>L: 条款结构化抽取（失败降级为段落分割）
    L-->>G: 结构化条款 + 风险预分类
    G-->>U: NODE_COMPLETE extractor

    G-->>U: NODE_START retriever
    G->>R: search_laws 混合检索（双路召回 + RRF → 精排）
    R-->>G: Top-K 法条（可溯源到具体条文）
    G-->>U: NODE_COMPLETE retriever

    G-->>U: NODE_START reviewer
    G->>L: 逐条风险评级 + 100 分制评分（失败降级规则引擎）
    L-->>G: 风险条目 + 法条依据 + 话术
    G-->>U: RISK_FOUND 逐条推送

    G-->>U: NODE_START negotiator
    G->>L: 为缺失项补全谈判话术
    G-->>U: SUMMARY + COMPLETE
```

各智能体通过 `graph.astream` 推进：节点内产生的 `NODE_START / THINKING / NODE_COMPLETE / RISK_FOUND` 事件按序累积进 `state.events`，runner 增量回放——线性与多智能体两种拓扑都保持「节点开始 → 思考 → 完成」的时间线语义。`NODE_START` 由各节点自行推送，因此条件边返工时也能正确回放多一轮事件。任一节点异常不中断全图：子智能体捕获错误写入 `state.errors` 并转为 `THINKING` 警告事件继续执行。

---

### 5.2 MinerU 版面解析 + 多模态视觉模型（文档接入层）

> 目标：把复杂版面的合同 PDF 稳定变成 LLM 可读、可溯源的 Markdown，而不是靠 `pypdf.extract_text()` 硬抽。完整实现见 `backend/app/services/mineru_parser.py`。

**链路**：`上传 PDF` → `MinerU 版面检测 / 阅读顺序还原 / 表格·公式识别 / OCR` → `Markdown + content_list 结构化块` → `图片块交多模态视觉模型补识` → `text_extractor → ExtractorAgent 条款结构化 → 混合检索 RAG → Reviewer`。

**三种策略（`PDF_PARSER_STRATEGY`）**

| 策略 | 行为 |
|---|---|
| `auto`（默认） | 探测到本机 MinerU CLI 或配置了内网解析服务就走 MinerU；不可用 / 超时 / 输出为空自动回退内置 `pypdf + PyMuPDF + OCR` 逐页混合链路，回退原因写入 `parse_meta.fallback_reason` |
| `mineru` | 强制 MinerU，不可用直接 503（fail-loud，不接受「看起来解析成功、实际是空文本」的假阴性） |
| `legacy` | 完全关闭 MinerU，走内置链路（含跨页表格合并 / 多栏栏感知） |

**两个后端（`MINERU_BACKEND`）**

- `cli`（`auto` 优先）：4.x `mineru-kit parse <pdf> -o result.md --tier standard`，2.x/3.x `mineru -p <pdf> -o <dir> -m auto`；收集 `*.md`、`*_content_list.json` 与 `images/`。
- `http`：调用内网自建服务 `POST /v1/file_parse`（`backend/scripts/mineru_http_server.py`，纯标准库实现，默认只监听 `127.0.0.1`，可选 Bearer Token），返回 `{markdown, content_list, images(base64)}`。适合把模型权重放在独立 CPU/GPU 节点、多台 backend 共享。

**结构化结果归一化**：`mineru_parser.py` 把 content_list 的 `text / title / table / image / equation` 统一成 `MinerUBlock`（表格 HTML → `单元格 | 单元格` 纯文本），并在临时目录清理前把图片字节读进内存；只有 Markdown 时按空行与图片引用切粗粒度块。兼容 MinerU 2.x/3.x `content_list.json` 与 4.x Content List V1/V2 的字段差异，CLI 与 HTTP 两后端共用同一套归一化逻辑。

**多模态视觉补识（`MINERU_VISION_ENRICH`）**：MinerU 负责「切出图片块」，多模态视觉大模型（默认 `qwen-vl-max-latest`）负责「读懂图片里是什么」——公章、签名、手写批注、表格截图、证照。识别文本以 `【图片内容·多模态识别】` 回填到 Markdown 原位置；未识别的临时图片路径被清成 `【图片区块】`，避免下游 LLM 看到失效引用。单份文档最多补识 `MINERU_VISION_MAX_IMAGES`（默认 6）张以控成本与时延；视觉模型失败只记 warning，不影响版面解析主文本。整页拍照件 / 扫描 PDF 仍走原有 `IMAGE_OCR_STRATEGY`（`auto` → 视觉 LLM → Tesseract）。

**隐私边界**：MinerU 是可选能力，默认本机 CLI 或内网 HTTP，合同原件不会上传任何公网解析服务；只有图片块会（按配置）送到视觉模型 API，与「推理私有化」口径一致（可切本地 vLLM / Ollama 视觉模型）。

**可观测**：`POST /api/v1/ingest/file` 响应新增 `parse_meta`：`{parser, detail, blocks, images, vision_enriched, fallback_reason}`，前端与后端复用同一份事实，不会出现「日志说降级、界面说成功」的口径分裂。

**降级矩阵**

| 场景 | `auto` | `mineru` | `legacy` |
|---|---|---|---|
| CLI / HTTP 都不可用 | 回退内置链路 + 记录原因 | 503 | 内置链路 |
| CLI 超时 / 非零退出 / 输出为空 | 回退内置链路 + 记录原因 | 503 | 内置链路 |
| 视觉模型未配置 / 调用失败 | 版面文本保留，图片块标占位 | 同左 | 不涉及 |
| MinerU 正常 | Markdown + 结构化块 + 视觉补识 | 同左 | 内置链路 |

---

## 六、Agent 与 MCP 架构

### 6.1 多智能体协作工作流（6 个自治智能体 + 条件返工）

```
StateGraph(AgentState) · AGENT_MODE=multi (默认)
 │   START
 ▼
 ├─ 🧭 coordinator  — CoordinatorAgent（自治编排: 定参与方 / 逐个下发 task 消息）
 │     └─ agent_plan = [extractor, retriever, reviewer, verifier, negotiator]
 ▼
 ├─ 📝 extractor    — ExtractorAgent  （文本抽取/OCR纠错/条款结构化）
 ├─ 📚 retriever    — RetrieverAgent  （混合法规检索 RAG）
 ├─ ⚖️ reviewer     — ReviewerAgent   （风险审查/评分）
 ▼
 ├─ 🧪 verifier     — VerifierAgent   （独立复核: 原文定位 + 法条溯源交叉验证）
 │     ├─ 不通过 → 给 reviewer 发 rework 消息 ──┐
 │     │                                        │ 条件边回边 (≤ max_review_rounds)
 │     └────────────────────────────────────────┘
 │     └─ 通过/达上限 → 给 negotiator 发 handoff 消息
 ▼
 └─ 💬 negotiator   — NegotiatorAgent （谈判策略生成）
 ▼
 END

 每个智能体执行完广播 result 消息，全部协作轨迹落在 state.agent_messages。
 AGENT_MODE=linear 时退回旧四节点线性链（无 coordinator / verifier / 条件边）。
```

| 节点 / 子智能体 | key | 擅长场景 / 自治决策 |
|---|---|---|
| CoordinatorAgent | `coordinator` | 按合同规模决定参与智能体（极短文本跳过 verifier），通过消息总线下发 task；确定性规则保证编排可审计 |
| ExtractorAgent | `extractor` | 合同文本清洗、OCR 纠错、条款结构化拆分 |
| RetrieverAgent | `retriever` | 劳动法条文混合检索（双路召回 + RRF 融合 + 精排）、RAG 召回 |
| ReviewerAgent | `reviewer` | 风险多维度打分、法律依据生成；收到 rework 消息时重新审查 |
| VerifierAgent | `verifier` | 独立交叉核验原文定位与法条溯源；**可否决结论**并发起返工，通过后 handoff |
| NegotiatorAgent | `negotiator` | 补充谈判话术，确保每条风险都有应对策略 |

消息类型：`plan` / `task` / `result` / `rework` / `handoff`，均带 `sender`、`recipient`、`round`，可完整回溯「谁让谁重审、为什么」。

**额外独立智能体：**

| 智能体 | key | 用途 |
|---|---|---|
| ConsultantAgent | `consultant` | 独立于合同分析流的智能咨询模块，支持多轮对话、法条引用、追问建议 |

工作流实现在 `backend/app/agent/graph.py`（`build_contract_graph(mode)` 按模式编译图 + `run_contract_analysis` SSE 运行器），节点动作由 `_node_action` 统一包装——子智能体执行 + 消息广播 + 错误捕获 + 事件累积；条件边 `_route_after_review` / `_route_after_verify` 实现动态路由与返工闭环。

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
| `law_search` | 检索劳动法条文知识库，返回带相关度的片段 | `rag/vector_store.search_laws()`：双路召回（向量 Milvus + BM25）→ RRF → 精排 |
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
| `NODE_START` | `{node_name, description, progress}` | 节点开始执行（runner 按图顺序预推） |
| `NODE_COMPLETE` | `{node_name, description, progress}` | 节点执行完成 |
| `THINKING` | `{content}` | 节点出错时推送警告 |
| `RISK_FOUND` | `{category, level, title, explanation, ...}` | 逐条推送风险评估结果 |
| `SUMMARY` | `{overall_score, overall_level, summary, ...}` | 分析完成推送总计 |
| `ERROR` | `{message}` | 工作流级异常 |
| `COMPLETE` | — | 流程结束 |

### 6.6 A2A（Agent2Agent Protocol）

除 MCP 外，Lumos 同时实现了 **A2A 协议**，让本服务作为一个可被其他 Agent 发现并调用的「对等智能体」，而不仅仅是被 LLM 调用的工具集。

- 实现位于 `backend/app/a2a/`：`models.py`（协议数据模型）、`agent_card.py`（Agent Card 构建）、`executor.py`（复用 `run_contract_analysis` 工作流）、`routes.py`（端点）。
- 兼容 **Google A2A 规范 0.3.x**：`kind` 字段区分 Part 类型、标准 `Task`/`Artifact`/`TaskStatusUpdateEvent` 模型，并兼容新旧两套方法名（`message/*` 与 `tasks/*`）。
- 不依赖任何第三方 A2A SDK，纯 Pydantic 建模，便于在受限/离线环境部署。

| 端点 | 方法 | 说明 |
|---|---|---|
| `GET` | `/.well-known/agent.json` | 返回 Agent Card（能力自描述，供 A2A 客户端发现） |
| `POST` | `/a2a` | JSON-RPC 2.0 同步端点：`message/send`（或 `tasks/send`）提交合同文本，返回终态 `Task`（含风险清单 Artifact） |
| `POST` | `/a2a/stream` | SSE 流式 JSON-RPC：`message/stream`（或 `tasks/sendSubscribe`）逐阶段推送 `TaskStatusUpdateEvent` 与 `TaskArtifactUpdateEvent` |

**调用示例（A2A 同步）**

```bash
curl -X POST http://localhost:8000/a2a \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0", "id": 1, "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "（粘贴劳动合同正文）"}]
      }
    }
  }'
```

返回的 `result.artifacts` 含 `risk_assessments`（结构化 JSON）与 `report`（Markdown 报告），`result.status.state` 为 `completed`。

---

## 七、快速开始（Docker / 本地）

### 前置要求

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/)
- [Node.js](https://nodejs.org/) 18+（Web 端开发）
- [Flutter](https://flutter.dev/docs/get-started/install) 3.x+（移动端开发，可选）
- [Python](https://www.python.org/) 3.11+（服务端开发，可选）

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
| `front` | 本地构建 | 8080 → 80 | Nginx 托管 Web 前端 |

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
pip install -e ".[dev]"     # 主依赖已含 sentence-transformers / pymilvus / rank-bm25 / jieba
cp .env.example .env
# 编辑 .env 填入 AI API Key 等配置
uvicorn app.main:app --reload
```

> **本地 embedding 模型**：默认 `EMBEDDING_PROVIDER=local`，权重目录约定为扁平命名 `backend/models/bge-base-zh-v1.5/`（约 400MB，已在 `.gitignore` 中排除）。目录存在即直接加载（跳过 HF 探测）；缺失时按 `HF_ENDPOINT` 镜像自动下载。模型名写 `bge-base-zh-v1.5` 或 `models/bge-base-zh-v1.5` 均可被正确解析。

**Web 前端：**

```bash
cd front
npm install
npm run dev
```

> **Flutter 客户端（已归档，未纳入本仓库）**：遗留移动端代码原位于 `archive/client/`，现已归档并不包含在本仓库中，仅供历史参考。

> ⚠️ 本地网络无法直连 HuggingFace 时，embedding 模型下载可走镜像：`$env:HF_ENDPOINT='https://hf-mirror.com'`（PowerShell）或 `export HF_ENDPOINT=https://hf-mirror.com`（bash）。

---

### 7.3 方式三（可选）：启用 MinerU 版面解析

MinerU 是**可选能力**：不安装时 PDF 走内置 `pypdf + PyMuPDF + OCR` 链路，服务照常启动；装上后 `PDF_PARSER_STRATEGY=auto`（默认）会自动启用。

```bash
# 1) 在独立 venv 安装 MinerU 4.x (Python 3.11~3.14, 模型权重首次按需下载)
uv venv .mineru --python 3.12
uv pip install -U "mineru>=4.0,<5"
mineru-kit parse contract.pdf -o contract.md --tier standard   # 先单独验证 CLI 可用

# 2) 本机 CLI 模式 (默认): 让 backend 能找到可执行文件
#    MINERU_BACKEND=cli
#    MINERU_CLI=/abs/path/to/mineru-kit   # 留空则自动探测 PATH 中的 mineru-kit / mineru
#    MINERU_CLI_FLAVOR=auto               # 2.x/3.x 用户显式设 v2

# 3) 内网 HTTP 模式: 在装了 MinerU 的机器上启动零依赖适配服务 (默认只监听 127.0.0.1)
python backend/scripts/mineru_http_server.py --cli mineru-kit --port 8100 --token mytoken
#    MINERU_BACKEND=http
#    MINERU_HTTP_URL=http://127.0.0.1:8100/v1/file_parse
#    MINERU_HTTP_TOKEN=mytoken

# 4) 图片块交给多模态视觉模型补识 (默认开)
#    MINERU_VISION_ENRICH=true
#    MINERU_VISION_MAX_IMAGES=6
#    LLM_VISION_API_KEY=...               # 未配置则图片块只保留占位, 不影响版面文本
```

> 需要「必须走 MinerU」的验收环境设 `PDF_PARSER_STRATEGY=mineru`：解析不可用会返回 503，而不是静默降级成质量更差的结果。完整配置项见 §九。

---

## 八、测试、评测与量化口径

### 8.1 自动化测试与覆盖率

```bash
cd backend
python -m pytest                       # 全部用例（单元 + 冒烟）
python -m pytest --cov=app             # 覆盖率（HTML 报告输出至 htmlcov/）
python -m pytest -m "not e2e"          # 跳过需要真实模型/服务的用例
LUMOS_E2E=1 python -m pytest -m e2e    # 端到端检索链路用例（需 embedding 模型就绪）
```

- 当前 **140+ 条 pytest 用例**（含 7 条多智能体协作测试：`backend/tests/test_multi_agent.py`）（其中 14 条为 MinerU 版面解析 / 视觉补识 / 回退分支，2 条 e2e 需 `LUMOS_E2E=1`），覆盖：**MinerU CLI/HTTP 两后端、content_list 归一化、图片块视觉补识、auto 回退与 fail-loud**（见 `backend/tests/test_mineru_parser.py`）、API 冒烟、BM25 分词与领域词典、RRF 混合融合、向量通道异常时仅 BM25 降级兜底、LangGraph 状态流转与错误恢复、扫描/混排 PDF 逐页混合 OCR 分支、A2A 协议适配层、表格跨栏合并、多栏栏感知抽取、Embedding/Chroma 降级兜底（见 `backend/tests/`）；
- **MinerU 相关 14 条用例全部可离线运行**：以打桩的 `subprocess.run`、假 httpx 模块、假 pypdf 注入，不依赖真实 MinerU 模型权重、网络或视觉 API Key；`tests/conftest.py` 把 PDF 策略默认固定为 `legacy`，保证既有 OCR / 版面用例不受「开发机是否装有 MinerU」影响。
- 单元测试曾真实发现并修复两个生产缺陷：rank_bm25 查询需预分词（逐字符迭代产生伪分数）、jieba 需注册法律领域词典（「竞业限制」被错误切词）。

### 8.2 离线检索效果评测（hit@k / MRR）

```bash
cd backend
python -m eval.retrieval_eval --topk 5   # 输出 backend/eval/output/retrieval_eval_latest.{md,json}
```

评测以 `data/contracts/` 下 **90 份单分类金标准合同**（高危/警惕/关注三区 × 9 类风险 × 10 份）为样本：从合同文本抽取风险句作为查询，分别跑 **向量 / BM25 / 混合** 三个通道，统计 `hit@1/3/5` 与 `MRR@5`。**2026-09-09 实测**（本地 BAAI/bge-base-zh-v1.5，768 维，29 条法条文语料）：

| 通道 | hit@1 | hit@3 | hit@5 | MRR@5 |
| :--- | :--- | :--- | :--- | :--- |
| 向量（真实 embedding） | 0.489 | 0.656 | 0.833 | 0.613 |
| BM25（jieba 领域词典） | 0.322 | 0.433 | 0.700 | 0.437 |
| 混合（RRF 融合） | 0.389 | 0.789 | **0.878** | 0.585 |

如实解读：榜首精度（hit@1 / MRR@5）纯向量最好、融合次之、BM25 最后——29 条小语料下 BM25 噪音会拉低融合榜首；但 **RRF 融合的广度优势在 hit@3 / hit@5 上显著**：0.789 / **0.878**，均超过纯向量（0.656 / 0.833）。调优 `rrf_k` 是后续方向（重新运行本命令即可复现最新数字）。

> **注**：上表为 2026-09-09 在 29 条小语料上的历史基线。此后语料已扩充至 **18 部现行劳动法规、670 条条文**（14 部完整条文 JSON 位于 `backend/app/rag/data/`，另并入民法典 / 个人信息保护法 / 医疗期 / 劳务派遣等扩展条文，见 `app/rag/law_corpus_ext.py`），向量索引按内容哈希自动重建；上表数字待重跑评测后更新。

### 8.3 量化口径边界

请严格区分两类指标：

- **开发规模指标**：`backend/app` 行数、模块数、测试语料份数、用例条数等——它们只能说明交付体量与工程完备度；
- **效果指标**：检出率 / 准确率 / `hit@k` / `MRR` / 时延——必须由评测脚本跑出真实数字（如 8.2），仓库内所有宣称的效果均可通过 `backend/eval/` 复现。

任何将「写了 XX 行代码 / 建了 XX 份语料」表述为「准确率达 XX%」的说法都是口径错误。

---

## 九、环境变量

> 完整模板见根目录 `.env.example`（Docker Compose 用）与 `backend/.env.example`（本地后端用）。

| 分组 | 变量 | 默认值 | 说明 |
|---|---|---|---|
| 应用 | `APP_ENV` | `development` | 运行环境 |
| | `LOG_LEVEL` | `DEBUG` | 日志级别 |
| 数据库 | `DATABASE_URL` | `mysql+aiomysql://lumos:lumos@localhost:3306/lumos` | MySQL 连接串（Docker 部署时宿主端口为 3308） |
| SQL 回显 | `DATABASE_ECHO` | `false` | 是否在日志回显执行 SQL（调试用；默认关闭避免刷屏） |
| LLM | `LLM_API_KEY` | （必填） | AI 模型 API Key |
| | `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容接口地址 |
| | `LLM_MODEL_NAME` | `deepseek-chat` | 模型名称 |
| Embedding | `EMBEDDING_PROVIDER` | `local` | `local`（sentence-transformers 本地）\| `api`（OpenAI 兼容 /embeddings） |
| | `EMBEDDING_MODEL_NAME` | `BAAI/bge-base-zh-v1.5` | 模型名（`api` 模式为接口模型 ID） |
| | `EMBEDDING_API_KEY` | （空） | `api` 模式密钥 |
| | `EMBEDDING_BASE_URL` | `https://api.deepseek.com/v1` | `api` 模式接口地址 |
| | `EMBEDDING_DIM` | （空） | 手动指定向量维度；留空则由模型自动探测 |
| | `EMBEDDING_QUERY_INSTRUCTION` | （空，按模型自动） | 检索 query 前缀指令；BGE 系列自动加中文指令、文档侧不加，非 BGE 模型不追加 |
| | `HF_ENDPOINT` | `https://hf-mirror.com` | 本地模型权重缺失时的下载镜像（huggingface.co 受限时使用） |
| 混合检索 | `HYBRID_TOP_K_RATIO` | `2` | 融合前各通道候选数 = top_k × 该值 |
| | `RRF_K` | `60` | RRF 融合参数：score = Σ 1/(k + rank) |
| | `HYBRID_VECTOR_WEIGHT` | `0.65` | 相关度分数中向量通道权重（BM25 权重 = 1 − 该值） |
| | `HYBRID_SINGLE_CHANNEL_FACTOR` | `0.85` | 仅单通道命中时的相关度折扣（0~1） |
| 精排 | `RERANKER_ENABLED` | `false` | 是否启用 CrossEncoder 语义精排（关闭时回退轻量可解释精排） |
| | `RERANKER_MODEL_NAME` | `BAAI/bge-reranker-base` | CrossEncoder 精排模型 |
| | `RERANKER_CANDIDATE_MULTIPLIER` | `3` | 精排前候选池 = top_k × 该值（与 `HYBRID_TOP_K_RATIO` 取大） |
| | `RERANKER_MAX_LENGTH` | `512` | CrossEncoder 单条输入最大长度 |
| | `RETRIEVAL_MIN_SIMILARITY` | `0.05` | 精排后 `final_score` 低于该阈值的命中被过滤 |
| 视觉 OCR | `LLM_VISION_API_KEY` / `LLM_VISION_BASE_URL` / `LLM_VISION_MODEL_NAME` | qwen-vl / DashScope | 图片文字抽取（未配置时回退 Tesseract） |
| | `IMAGE_OCR_STRATEGY` | `auto` | `auto` \| `llm` \| `tesseract` |
| MinerU 版面解析 | `PDF_PARSER_STRATEGY` | `auto` | `auto`（不可用回退并记录原因） \| `mineru`（强制，不可用 503） \| `legacy`（关闭） |
| | `MINERU_BACKEND` / `MINERU_CLI` / `MINERU_CLI_FLAVOR` | `auto` / 空 / `auto` | 后端 `cli` \| `http` \| `auto`（CLI 优先）；CLI 路径与版本风味 `v4` / `v2` |
| | `MINERU_TIER` / `MINERU_METHOD` / `MINERU_TIMEOUT_SECONDS` | `standard` / `auto` / `180` | 4.x 解析档位（flash/basic/standard/advanced）/ 2.x 方法 / 超时秒数 |
| | `MINERU_HTTP_URL` / `MINERU_HTTP_TOKEN` | （空） | 内网解析服务地址与可选 Bearer Token；留空则不启用 HTTP 后端 |
| | `MINERU_VISION_ENRICH` / `MINERU_VISION_MAX_IMAGES` | `true` / `6` | 版面图片块交多模态视觉模型补识 / 单份文档补识上限 |
| 安全 | `API_SECRET_KEY` | （空，置空关闭鉴权） | 业务鉴权密钥 |
| | `JWT_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Token 过期时间（7 天） |
| Milvus | `MILVUS_HOST` / `MILVUS_PORT` | `localhost:19530` | 向量数据库地址 |
| | `MILVUS_COLLECTION` | `labor_laws` | 集合**基名**；实际集合 = 基名 + embedding 签名，换模型自动隔离重建 |
| MinIO | `MINIO_ENDPOINT` | `localhost:9000` | 对象存储地址 |
| | `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `minioadmin` | 访问密钥 |
| | `MINIO_BUCKET` | `lumos` | 存储桶名称 |

---

## 十、API 一览

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
| A2A 协议 | `GET` | `/.well-known/agent.json` | Agent Card（能力自描述） |
| | `POST` | `/a2a` | A2A JSON-RPC 同步端点（message/send） |
| | `POST` | `/a2a/stream` | A2A SSE 流式端点（message/stream） |
| 智能导入 | `POST` | `/api/v1/ingest/file` | 上传文件抽取文本（16 种格式 + OCR；PDF 可选 MinerU 版面解析 + 视觉模型补识），响应含 `parse_meta` 解析链路元信息 |
| | `POST` | `/api/v1/ingest/url` | 抓取网页抽取正文 |
| 智能咨询 | `POST` | `/api/v1/consult/ask` | 发起智能咨询（SSE 流式） |
| | `GET` | `/api/v1/consult/sessions` | 会话列表 |
| | `GET` | `/api/v1/consult/sessions/{id}/messages` | 会话消息记录 |
| | `DELETE` | `/api/v1/consult/sessions/{id}` | 删除会话 |

> 完整 OpenAPI 文档在本地启动后端后访问 `http://localhost:8001/docs`。

---

## 十一、项目结构

```
lumos/
├── README.md                          # 项目说明
├── docker-compose.yml                 # 一键部署（MySQL/MinIO/Milvus/后端/Web）
├── .env.example                       # 环境变量模板
├── .gitignore
│
├── （archive/client/ 遗留 Flutter 移动端已归档，未纳入本仓库）
│
├── front/                             # Vue 3 Web 前端
│   ├── src/
│   │   ├── api/                       # API 接口封装（auth/client/contract/consult/ingest）
│   │   ├── layouts/                   # 布局组件
│   │   ├── router/                    # 路由与登录守卫
│   │   ├── stores/                    # Pinia 状态管理
│   │   ├── utils/                     # 通用工具
│   │   ├── views/                     # 页面（Dashboard/Analysis/Reports/Consult/MCP/Login/Register）
│   │   ├── App.vue
│   │   └── main.ts
│   ├── shots/                         # Web 端功能截图（README §三 引用）
│   └── Dockerfile + nginx.conf        # Nginx 托管 + SSE 长连接代理（关闭缓冲/放宽超时）
│
├── backend/                           # Python FastAPI 服务端
│   ├── app/
│   │   ├── agent/                     # LangGraph 编排层
│   │   │   ├── graph.py               # StateGraph 构建 + SSE 运行器 run_contract_analysis
│   │   │   ├── state.py               # LangGraph AgentState（共享状态 + 消息总线 + events 通道）
│   │   │   ├── base.py                # 子智能体抽象基类 BaseAgent
│   │   │   ├── llm.py                 # LLM 客户端工厂（ChatOpenAI / Vision）
│   │   │   └── sub_agents/            # Coordinator/Extractor/Retriever/Reviewer/Verifier/Negotiator/Consultant
│   │   ├── rag/                       # 混合检索（真实 embedding + 双路召回 + RRF + 精排）
│   │   │   ├── embeddings.py          # 双 Provider embedding（local / API），签名隔离
│   │   │   ├── milvus_store.py        # Milvus 集合管理 + 检索（COSINE/动态维度）
│   │   │   ├── vector_store.py        # 混合检索入口 search_laws（双路召回 → RRF → 精排）
│   │   │   ├── bm25_index.py          # BM25 全文检索（jieba 分词 + 法律领域词典）
│   │   │   ├── hybrid.py              # RRF 融合（Reciprocal Rank Fusion）
│   │   │   ├── reranker.py             # 精排（可解释 / CrossEncoder）+ 阈值过滤
│   │   │   └── law_corpus.py          # 劳动法规条文语料（内容哈希）
│   │   ├── api/v1/                    # FastAPI 路由
│   │   ├── core/                      # 配置、数据库、安全、MinIO
│   │   ├── mcp/                       # MCP 协议（Server/Client/Tools）
│   │   ├── a2a/                       # A2A 协议（Agent Card / JSON-RPC / SSE）
│   │   ├── models/                    # 数据模型（SQLModel）
│   │   ├── schemas/                   # Pydantic 出入参 / SSE 事件协议
│   │   ├── services/                  # 文本摄取（16 种格式 + OCR + MinerU 版面解析）
│   │   │   ├── mineru_parser.py       # MinerU CLI/HTTP 适配、content_list 归一化、视觉补识
│   │   │   └── text_extractor.py      # 统一抽取入口 + PDF 策略分流 + 内置 OCR 回退
│   │   └── skills/                    # 可复用技能
│   ├── scripts/
│   │   └── mineru_http_server.py      # 内网 MinerU 解析服务（标准库，零第三方依赖）
│   ├── eval/                          # 离线检索评测（hit@k / MRR，金标准语料）
│   │   └── retrieval_eval.py
│   ├── tests/                         # 100+ 条 pytest 用例（2 条 e2e marker）
│   ├── models/                        # 本地 embedding 权重（bge-base-zh-v1.5，已 gitignore）
│   ├── logs/                          # 运行日志（每日轮转/保留 30 天，已 gitignore）
│   ├── pyproject.toml
│   └── .env.example
│
├── docs/                              # 项目文档
│   └── technical-design.md            # 技术设计方案（早期基线 + 实现现状对照附录 A/B）
│
├── data/contracts/                    # 测试语料（100 份中文合同：高危/警惕/关注/综合 4 区）
│
├── CHANGELOG.md                       # 更新日志
├── CONTRIBUTING.md                    # 贡献指南
├── SECURITY.md                        # 安全政策
├── CODE_OF_CONDUCT.md                 # 行为准则
└── LICENSE                            # Apache-2.0
```

**文档导航**

| 文档 | 内容 |
|:---|:---|
| `README.md`（本文） | 项目总览、系统架构、快速开始、测试评测、API、环境变量 |
| `docs/technical-design.md` | 技术设计方案（早期设计基线 + 实现现状对照附录 A/B） |
| `backend/README.md` | 服务端模块说明、检索链路、测试与评测命令 |
| `front/README.md` | Web 前端结构、开发代理与构建部署 |
| `CHANGELOG.md` | 版本更新日志（Keep a Changelog 格式） |
| `CONTRIBUTING.md` / `SECURITY.md` / `CODE_OF_CONDUCT.md` | 贡献指南 / 安全政策 / 行为准则 |

---

## 十二、参与贡献

Lumos 是一个为劳动者发声的公益开源项目，我们需要多元化的力量：

- ⚖️ **法律从业者** — 完善判例库、优化风险检测规则
- 💻 **开发者** — 提交 PR，优化系统性能与 UI 细节
- 🧑 **每一个打工人** — 分享你踩过的坑，让 AI 学习并保护更多人

欢迎提交 Issue 或 Pull Request！详见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

## 十三、免责声明与许可证

### 免责声明

**契光鉴微** 是一款基于人工智能的辅助审阅工具。系统检测结果与话术仅供参考，**不构成具有法定效力的专业法律建议**。对于标的额巨大或情况极其复杂的劳动争议，建议您线下咨询专业持证律师。

### 许可证

本项目基于 [Apache 2.0 License](./LICENSE) 开源。Copyright © 2026 Lumos Contributors.

---

<p align="center">
  <strong>✨ 照见契约中最细微的陷阱</strong>
</p>
