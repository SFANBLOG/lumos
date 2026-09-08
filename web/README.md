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

```bash
cd web
npm install
npm run dev
```

## 项目结构

```
web/
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

```bash
npm run build          # 产物输出至 dist/
```

容器化部署可使用仓库根目录的 `docker-compose.yml`（`docker compose up -d --build web`）。
