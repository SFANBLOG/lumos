# 📋 更新日志

所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [0.2.1] - 2026-09-09

### 🔄 Embedding 模型升级
- 默认本地模型 `paraphrase-multilingual-MiniLM-L12-v2`（384 维）→ **`BAAI/bge-base-zh-v1.5`**（768 维中文检索）。
- 模型权重落盘为扁平目录 `backend/models/BAAI/bge-base-zh-v1.5/`（宿主机持久化，容器只读挂载），不再使用 HF hub-cache 式 `snapshots/` 结构。
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
- 🔀 重构 `vector_store.py`：`search_laws()` 混合检索入口（向量 → Milvus/Chroma 降级 + BM25 → RRF），`_channel` 通道打标归一
- 🐛 修复生产缺陷：rank_bm25 查询须预分词（逐字符迭代产生伪分数）、Chroma 降级路径通道未打标

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
