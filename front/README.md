# 💻 Lumos Web

Lumos 契光鉴微 - Vue 3 + TypeScript Web 前端

## 技术栈

- Vue 3 + TypeScript
- Vite
- Pinia
- Vue Router 4
- Axios
- Element Plus

## 快速开始

> 要求 **Node.js 18+**。

```bash
cd front
npm install
npm run dev        # http://localhost:5173
```

开发态已配置代理（`vite.config.ts`）：`/api` → `http://localhost:8001`，因此本地调试只需先启动后端即可，无需处理跨域。

```bash
npm run build      # vue-tsc 类型检查 + 产物输出至 dist/
npm run preview    # 本地预览构建产物
```

## 项目结构

```
front/
├── Dockerfile           # 生产镜像 (nginx)
├── nginx.conf
├── src/
│   ├── api/             # API 接口封装
│   │   ├── auth.ts      # 注册 / 登录 / 当前用户
│   │   ├── client.ts    # Axios 实例与拦截器
│   │   ├── contract.ts  # 合同分析与报告
│   │   ├── consult.ts   # 智能咨询 (SSE)
│   │   └── ingest.ts    # 文件 / URL 导入
│   ├── layouts/         # 布局组件 (AppLayout.vue)
│   ├── router/          # 路由与登录守卫
│   ├── stores/          # Pinia 状态管理
│   │   ├── auth.ts
│   │   └── consult.ts
│   ├── utils/           # 通用工具 (contractMeta.ts)
│   ├── views/           # 页面
│   │   ├── LoginView.vue / RegisterView.vue
│   │   ├── DashboardView.vue    # 工作台
│   │   ├── AnalysisView.vue     # 合同分析
│   │   ├── ReportsView.vue      # 报告中心
│   │   ├── ConsultView.vue      # 智能咨询
│   │   └── MCPView.vue          # MCP 工具箱
│   ├── App.vue
│   └── main.ts
└── shots/               # 功能截图
```

## 构建与部署

容器化部署使用仓库根目录的 `docker-compose.yml`（宿主端口 `8080 → 容器 80`）：

```bash
docker compose up -d --build front    # Nginx 托管 dist/ 产物
```

`nginx.conf` 关键点：

- SPA 回退：`try_files $uri $uri/ /index.html`；
- `/api` 反向代理到 `backend:8000`，并**关闭 `proxy_buffering`、放宽读写超时至 3600s**——合同分析/智能咨询走 SSE 长连接，不这样配置会在 60s 被掐断。

## 页面与截图

| 页面 | 文件 | 截图 |
|:---|:---|:---|
| 登录 / 注册 | `LoginView.vue` / `RegisterView.vue` | `shots/login.png` |
| 工作台 | `DashboardView.vue` | `shots/dashboard.png` |
| 合同分析 | `AnalysisView.vue` | `shots/analysis-result.png` |
| 报告中心 | `ReportsView.vue` | `shots/report-drawer.png` |
| 智能咨询 | `ConsultView.vue` | `shots/consult-3-answering.png` |
| MCP 工具箱 | `MCPView.vue` | `shots/mcp-1-law-search.png` |

> `shots/` 共 23 张功能截图，覆盖登录、分析、咨询全流程与生产环境演练。
