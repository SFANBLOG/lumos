# 📋 更新日志

所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 🧩 MinerU 版面解析 + 多模态视觉模型接入（可选、可降级）

- ➕ 新增 `backend/app/services/mineru_parser.py`：MinerU 版面解析适配层，支持本机 CLI（4.x `mineru-kit parse` / 2.x `mineru -p`）与内网 HTTP 服务两种后端；统一收集 `*.md`、`*_content_list.json` 与 `images/`，把 `text/title/table/image/equation` 归一化为 `MinerUBlock`（表格 HTML → `单元格 | 单元格` 纯文本）
- 🤖 **多模态视觉模型联动**：MinerU 切出的公章/签名/手写批注/表格截图等图片块交给视觉大模型（默认 `qwen-vl-max-latest`）补识，识别文本以 `【图片内容·多模态识别】` 回填 Markdown 原位置；未识别的临时图片路径清成占位，避免下游 LLM 看到失效引用；`extract_image_via_llm` 新增可选 `prompt` 参数区分整页 OCR 与图片块识别
- 🔌 `text_extractor.extract_pdf` 拆为 `extract_pdf_detailed`（带解析元信息）与 `_extract_pdf_legacy`（原内置 pypdf + PyMuPDF + OCR 逐页混合链路）；新增 `extract_by_ext_detailed`，`POST /api/v1/ingest/file` 响应新增 `parse_meta`（parser / detail / blocks / images / vision_enriched / fallback_reason）；前端 `AnalysisView` 同步展示解析引擎 / 视觉补识数 / 回退提示，`ParseMeta` 类型见 `front/src/api/ingest.ts`
- 🛡️ **三策略与 fail-loud**：`PDF_PARSER_STRATEGY=auto`（默认，不可用自动回退并记录原因）/ `mineru`（强制，不可用返回 503，不接受空文本假阴性）/ `legacy`（关闭）；CLI 超时、非零退出、输出为空均显式降级，不会出现「看起来成功实则没解析」
- 🌐 新增 `backend/scripts/mineru_http_server.py`：纯标准库实现的内网解析服务（`POST /v1/file_parse`），默认只监听 `127.0.0.1`，支持可选 Bearer Token 与 PDF magic bytes 校验；便于把模型权重部署在独立 CPU/GPU 节点
- ⚙️ 新增 11 个配置项（`PDF_PARSER_STRATEGY` / `MINERU_BACKEND` / `MINERU_CLI` / `MINERU_CLI_FLAVOR` / `MINERU_TIER` / `MINERU_METHOD` / `MINERU_HTTP_URL` / `MINERU_HTTP_TOKEN` / `MINERU_TIMEOUT_SECONDS` / `MINERU_VISION_ENRICH` / `MINERU_VISION_MAX_IMAGES`），根 `.env.example` 与 `backend/.env.example` 同步；`pyproject.toml` 新增可选 `mineru` extra，不装不影响服务启动
- 🧪 新增 14 条离线用例（`tests/test_mineru_parser.py`）：CLI 两版本命令形态、产物收集、失败/超时、content_list 归一化、视觉补识成功与失败、HTTP JSON 解析、auto 回退 / mineru fail-loud / 正常解析三分支；`tests/conftest.py` 固定单测默认 `legacy`，避免开发机环境差异影响既有 PDF 断言
- 🔧 顺带补齐内置 PDF 回退链路：`PDF_CROSS_PAGE_TABLE_MERGE` / `PDF_LAYOUT_GEOMETRY` / `PDF_COLUMN_AWARE_EXTRACT` 三个配置开关与跨页表格合并、多栏栏感知抽取接线（此前 `table_layout.py` / `table_merge.py` 与测试已存在但未接入 `extract_pdf`，导致 3 条既有测试失败），使两份工作副本的 PDF 链路保持一致
- 📝 README 新增 §5.2「MinerU 版面解析 + 多模态视觉模型」与 §7.3 可选安装说明，补齐技术栈、环境变量、API、项目结构与测试口径

### 🔍 混合检索相关度分数优化

- 🐛 **修复 Milvus COSINE 分数语义反转**：COSINE 度量的 `distance` 字段即余弦相似度（越大越相似），旧代码 `1 - distance` 导致得分与相关度背离；现直接裁剪至 [0, 1] 输出
- 🧹 **BM25 过滤零分未命中文档**：查询词全未命中的文档此前仍进入 RRF 候选池并贡献名次分，稀释真实相关命中；现按分数降序在零分处截断，并新增 `__len__` 便于语料量断言
- 📊 **相关度分数升级为通道真实分数加权**：`similarity` 从「仅位次常量」（双通道命中固定 0.5、单通道 0.3333…）改为 `HYBRID_VECTOR_WEIGHT`（默认 0.65）× 向量余弦 + 0.35 × BM25 通道内归一分；仅单通道命中时乘 `HYBRID_SINGLE_CHANNEL_FACTOR`（默认 0.85）折扣；无分数命中保留位次置信度兜底。真实链路实测：双通道命中 0.67~0.75、单通道向量命中 0.43~0.53，区分度显著提升
- ⚙️ 新增配置项 `HYBRID_VECTOR_WEIGHT` / `HYBRID_SINGLE_CHANNEL_FACTOR`，根 `.env.example` 与 `backend/.env.example` 同步
- 🧪 新增检索用例（无关查询返回空、双通道加权分数、单通道折扣）；检索 18 条 + 工作流 4 条测试全绿，离线评测三通道 hit@k/MRR 无回归

---

## [0.2.2] - 2026-09-10

### 🔧 工程健壮性与运维

- 🗄️ **Milvus 迁移至 `MilvusClient` 客户端 API**：`Collection.*` ORM-style 调用（`insert` / `flush` / `num_entities` / `search`）全部替换为客户端 API（`create_schema` / `prepare_index_params` / `insert` / `search` / `get_collection_stats`），消除 PyMilvus 3.x `PyMilvusDeprecationWarning`，向前兼容 PyMilvus 3.1+
- 📝 **日志改造**：新增 `DATABASE_ECHO` 配置（默认 `false`），开发环境不再回显 SQL 刷屏；标准库 `sqlalchemy.*` 日志器默认收敛至 WARNING；日志文件由「仅生产」改为**开发/生产均落盘** `backend/logs/lumos_<日期>.log`（每日零点轮转、保留 30 天、gz 压缩、UTF-8、路径锚定不依赖启动 CWD）
- 🐍 **Python 版本对齐**：`requires-python` / ruff `target-version` / mypy `python_version` 由 3.12 对齐到实际运行时 **3.11**，消除 IDE 对 `from __future__ import annotations` 的冗余告警
- 🧭 **embedding 路径解析修复**：新增 `_resolve_local_model()`，任意 CWD 下均可把 `bge-base-zh-v1.5` / `models/bge-base-zh-v1.5` / `BAAI/bge-base-zh-v1.5` 解析到本地权重目录并强制 `local_files_only=True`，彻底跳过 sentence-transformers 对 `modules.json` / `adapter_config.json` 的 HF HEAD 探测（国内网络下会超时 `WinError 10060`）
- 🧹 `.dockerignore` 排除 `logs/`；本地模型权重与运行日志均已 gitignore

### 📚 文档

- 🖼️ 根 README 与项目介绍文档补充 **Mermaid 架构图**（分层总览 / LangGraph + SSE 时序 / 混合检索 RRF 链路）
- 📐 全量文档校准：Python 版本（3.12→3.11）、文件格式数（16 种）、项目结构（移除不存在的 `public/`，补 `models/`、`logs/`、`shots/`）、依赖安装命令（移除不存在的 `embedding` extra）、Milvus/BM25 降级口径（无 ChromaDB）
- 🔐 `SECURITY.md` 修正与当前实现不符的隐私表述、报告入口改为 Gitee

---

## [0.2.1] - 2026-09-09

### 🔄 Embedding 模型升级
- 默认本地模型 `paraphrase-multilingual-MiniLM-L12-v2`（384 维）→ **`BAAI/bge-base-zh-v1.5`**（768 维中文检索）。
- 模型权重落盘为扁平目录 `backend/models/bge-base-zh-v1.5/`（宿主机持久化，容器只读挂载，兼容 `BAAI/bge-base-zh-v1.5` 等写法），不再使用 HF hub-cache 式 `snapshots/` 结构。
- 新增 BGE 检索约定：query 侧自动追加中文指令前缀（`embedding_query_instruction` 可覆盖），文档侧不加，提升语义召回精度。
- Milvus 集合按 embedding 签名自动隔离，换模型后自动创建新集合，无需手工重建。

---

## [0.2.0] - 2026-09-08

### ✨ Agent 引擎重构：真 LangGraph

- ⚙️ 以 **LangGraph 1.x StateGraph** 重写编排层：`agent/graph.py` 构建 extract → retrieve → review → negotiate 四节点线性图，节点共享 Pydantic `AgentState`（含 `events` 事件通道），`graph.astream` 增量回放 SSE 事件
- 🗑️ 删除自研 `supervisor.py` 手动 for 循环编排器，`run_contract_analysis` SSE 接口保持不变
- 🛡️ 节点级错误恢复：子智能体异常写入 `state.errors` → 转 `THINKING` 警告事件继续下一节点，全图失败才发 `ERROR`

### 🔍 RAG 混合检索 + 真实 Embedding

- 🧠 新增 `rag/embeddings.py`：**双 Provider 真实 embedding**——本地 sentence-transformers（默认 `paraphrase-multilingual-MiniLM-L12-v2`）/ OpenAI 兼容 API；向量按 embedding 签名隔离，换模型自动重建索引
- 🔎 新增 `rag/bm25_index.py`：法条语料 BM25 全文检索（jieba 分词 + 法律领域词典注册，修复「竞业限制」等法律术语切词）
- 🧩 新增 `rag/hybrid.py`：**RRF（Reciprocal Rank Fusion）融合**向量 + BM25 双通道排序
- 🗄️ 重构 `milvus_store.py`：动态维度（模型自动探测）、COSINE 度量、语料哈希 + embedding 签名双校验自动重建、集合名签名隔离
- 🔀 重构 `vector_store.py`：`search_laws()` 混合检索入口（向量 Milvus + BM25 → RRF），`_channel` 通道打标归一
- 🐛 修复生产缺陷：rank_bm25 查询须预分词（逐字符迭代产生伪分数）、降级路径通道未打标

> 注：该版本的向量降级后端曾短暂包含 ChromaDB，已在后续版本移除——现向量通道唯一后端为 Milvus，不可用时仅保留 BM25。

### 🧪 测试与效果评测

- 📈 新增检索链路与工作流单元测试（BM25 分词/领域词典、RRF 融合、Milvus 失败降级、LangGraph 状态流转与错误恢复）：pytest 用例 **6 → 27 条**（默认跑 25，另 2 条 e2e 需 `LUMOS_E2E=1`），`--cov` 行覆盖率 **~55%**（RAG 核心模块 70%+）
- 🎯 新增 `eval/retrieval_eval.py` 离线检索评测：`data/contracts` 90 份单分类金标准 × 9 类，分向量/BM25/混合三通道统计 hit@1/3/5 与 MRR@5
- 🏷️ pytest 新增 `e2e`/`retrieval` markers，`LUMOS_E2E=1` 触发真实链路用例

### 📚 文档与工程化

- 📝 重写根 README（架构图/技术栈/评测章节/量化口径边界）、`backend/README.md`（19 端点/env 变量/LangGraph/评测命令）
- 🔧 修复 `.env.example` 泄漏的真实密钥 → 占位符；补齐 embedding / 混合检索 / 视觉 OCR 配置项
- 📐 `docs/technical-design.md` 追加「实现现状对照（v0.6.0）」附录；CHANGELOG/简历口径同步
- 🚮 `.gitignore` 增加 `backend/eval/output/` 等

---

## [0.1.0] - 2026-03-09

### 🎉 初始发布

#### 新增
- 🏗️ 项目初始化，确立 Flutter + Python 双栈架构
- 📱 Flutter 客户端基础框架搭建
  - 首页、启动页、扫描页、报告页基础结构
  - Riverpod 状态管理 + go_router 路由
  - 主题系统与公共组件库
- 📄 技术设计方案 v0.4.0
- 📝 完整的开源社区配套文件
  - README（含项目介绍、架构图、技术栈）
  - CONTRIBUTING 贡献指南
  - CODE_OF_CONDUCT 行为准则
  - SECURITY 安全政策
  - CHANGELOG 更新日志

#### 规划中
- 🧠 Python AI 服务端（LangGraph Agent 引擎）
- 📸 端侧 OCR 集成（google_mlkit）
- 🔍 十大坑点智能检测算法
- 💬 "说人话" 条款解读
- 🗣️ 一键生成谈判话术

---

<p align="center">
  <sub>✨ 照见契约中最细微的陷阱</sub>
</p>
