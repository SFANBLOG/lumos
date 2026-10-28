# 契光鉴微 企业级运行基线

本版本提供 RBAC 角色（owner/admin/auditor/member）、只追加审计事件、请求关联 ID、限流、生产 CORS/Host 白名单及容器健康检查。

## 上线前必做

1. 设置 `APP_ENV=production`、强随机 `JWT_SECRET_KEY` 与 `API_SECRET_KEY`。
2. 设置 `CORS_ORIGINS`、`TRUSTED_HOSTS`，不要使用通配符。
3. 在首次注册前设置 `BOOTSTRAP_OWNER_EMAILS`；确认 owner 创建后再收紧该白名单。
4. 备份 MySQL，并执行一次滚动发布。`init_db` 仅创建新表；已有 `users` 表新增 `role` 列时需由 DBA 执行迁移：`ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member';`。
5. 审计记录不存合同正文、密码、Token 或 API Key；合规团队通过 `GET /api/v1/audit/events` 查询。

## 后续扩展

下一阶段应接入组织/工作区与 `tenant_id` 强制行级隔离、企业 SSO（OIDC/SAML）、SCIM、KMS 托管密钥、集中式指标/告警和独立异步任务队列。它们涉及身份提供商及数据迁移，应在租户模型确定后实施。
