# 📱 Lumos Client

Lumos 契光鉴微 - AI 劳动合同风险排查助手（Flutter 客户端）

## 技术栈

- Flutter 3.x (Dart)
- Riverpod (代码生成, 自动缓存)
- go_router
- Dio (SSE 流式分析)

## 快速开始

```bash
cd client
flutter pub get
flutter run
```

## 项目结构

```
client/lib/
├── core/
│   ├── api/           # API 客户端与服务
│   ├── providers/     # Riverpod Provider
│   ├── router/        # 路由配置
│   └── theme/         # 主题与配色
├── features/
│   ├── analysis/      # 合同分析流程
│   ├── home/          # 首页
│   ├── main/          # 底部导航脚手架
│   ├── mcp/           # MCP 工具调用
│   ├── report/        # 报告中心
│   ├── scanner/       # 扫描入口
│   └── splash/        # 启动页
└── shared/
    └── widgets/       # 公共组件
```
