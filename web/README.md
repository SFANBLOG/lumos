# 💻 Lumos Web

Lumos 契光鉴微 - Vue 3 Web 前端

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
web/src/
├── api/           # API 接口封装
│   ├── auth.ts
│   ├── client.ts
│   ├── contract.ts
│   └── mcp.ts
├── router/        # 路由与登录守卫
├── stores/        # Pinia 状态管理
│   ├── auth.ts
│   └── analysis.ts
├── views/         # 页面
│   ├── LoginView.vue
│   ├── RegisterView.vue
│   ├── HomeView.vue
│   ├── AnalysisView.vue
│   └── MCPView.vue
├── App.vue
└── main.ts
```

## 构建

```bash
npm run build
```

构建产物位于 `dist/` 目录。
