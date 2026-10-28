<template>
  <div class="qz-page">
    <PageHeader title="系统设置" description="管理账户信息、智能能力接入与数据安全策略。">
      <template #actions>
        <el-button type="primary" @click="ElMessage.success('设置已保存')">保存更改</el-button>
      </template>
    </PageHeader>

    <div class="settings-layout">
      <div class="settings-main">
        <section class="qz-panel account-card">
          <AppImage :src="avatar" width="64px" height="64px" radius="18px" :lazy="false" :alt="displayName" />
          <div class="account-meta">
            <div class="account-name">{{ displayName }}</div>
            <div class="account-sub">企业法务 · 契智法务工作区</div>
            <div class="account-tags">
              <span class="qz-chip qz-chip--primary">管理员</span>
              <span class="qz-chip qz-chip--muted">合同审查</span>
              <span class="qz-chip qz-chip--muted">规则维护</span>
            </div>
          </div>
          <el-button @click="ElMessage.info('账户信息编辑面板即将开放')">编辑资料</el-button>
        </section>

        <section class="qz-panel">
          <div class="qz-panel-head">
            <div>
              <div class="qz-panel-title">智能能力接入</div>
              <div class="qz-panel-sub">把 AI 审查、咨询与工具链连接到现有工作流</div>
            </div>
          </div>
          <div class="capability-grid">
            <button v-for="item in capabilities" :key="item.path" class="capability-card" @click="router.push(item.path)">
              <div class="qz-icon-box" :class="`qz-icon-box--${item.tone}`">
                <el-icon><component :is="item.icon" /></el-icon>
              </div>
              <div class="capability-meta">
                <div class="capability-title">{{ item.title }}</div>
                <div class="capability-desc">{{ item.desc }}</div>
              </div>
              <el-icon class="capability-arrow"><ArrowRight /></el-icon>
            </button>
          </div>
        </section>

        <section class="qz-panel">
          <div class="qz-panel-head">
            <div>
              <div class="qz-panel-title">安全与合规</div>
              <div class="qz-panel-sub">所有开关仅作用于当前工作区</div>
            </div>
          </div>
          <div class="switch-list">
            <div v-for="item in securityItems" :key="item.key" class="switch-row">
              <div>
                <div class="switch-title">{{ item.title }}</div>
                <div class="switch-desc">{{ item.desc }}</div>
              </div>
              <el-switch v-model="item.enabled" />
            </div>
          </div>
        </section>
      </div>

      <aside class="settings-side">
        <section class="qz-panel">
          <div class="qz-panel-head">
            <div class="qz-panel-title">最近操作</div>
          </div>
          <div class="audit-list">
            <div v-for="log in auditLogs" :key="log.id" class="audit-row">
              <span class="audit-dot" :class="`audit-dot--${log.tone}`" />
              <div class="audit-meta">
                <div class="audit-title">{{ log.title }}</div>
                <div class="audit-time">{{ log.time }}</div>
              </div>
            </div>
          </div>
        </section>

        <section class="qz-panel usage-card">
          <div class="qz-panel-title">本月额度</div>
          <div class="usage-value">1,284<span> / 2,000 份</span></div>
          <el-progress :percentage="64" :show-text="false" :stroke-width="8" color="#6c4cf1" />
          <p class="usage-tip">额度包含 AI 初审、规则命中与报告生成，剩余 716 份。</p>
          <el-button type="primary" plain style="width: 100%" @click="ElMessage.info('请联系管理员扩容')">
            申请扩容
          </el-button>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { markRaw, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowRight,
  ChatDotRound,
  Checked,
  MagicStick,
  Notebook,
} from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { avatarImage } from '@/utils/placeholder'

const router = useRouter()
const auth = useAuthStore()
const displayName = auth.user?.username ?? '林墨'
const avatar = ref(avatarImage(displayName))

const capabilities = [
  {
    path: '/consult',
    title: '智能咨询',
    desc: '劳动法与合同条款问答，自动引用法条依据',
    icon: markRaw(ChatDotRound),
    tone: 'primary',
  },
  {
    path: '/approvals',
    title: '审批队列',
    desc: '高风险结论的人工复核与审计留痕',
    icon: markRaw(Checked),
    tone: 'warn',
  },
  {
    path: '/playbooks',
    title: '审查标准',
    desc: '当前工作区生效的 Playbook 与执行规则',
    icon: markRaw(Notebook),
    tone: 'info',
  },
  {
    path: '/mcp',
    title: 'MCP 工具',
    desc: '法条检索、条款分析与风险评分能力标准化暴露',
    icon: markRaw(MagicStick),
    tone: 'success',
  },
]

const securityItems = reactive([
  { key: 'encrypt', title: '本地加密存储', desc: '合同原文与分析结果落盘前使用 AES-256 加密', enabled: true },
  { key: 'audit', title: '操作留痕', desc: '上传、审查、审批与导出全链路记录审计日志', enabled: true },
  { key: 'watermark', title: '导出水印', desc: '导出报告自动附加使用者与时间水印', enabled: false },
  { key: 'retention', title: '自动归档', desc: '审查完成后 180 天自动归档至历史报告库', enabled: true },
])

const auditLogs = [
  { id: 1, title: '导出「云服务采购框架协议」审查报告', time: '今天 10:02', tone: 'primary' },
  { id: 2, title: '启用规则「责任上限合理性检查」', time: '昨天 17:26', tone: 'success' },
  { id: 3, title: '更新知识库「采购合同审查指引 V3.2」', time: '09-08 14:10', tone: 'info' },
  { id: 4, title: '完成「品牌年度营销服务合同」人工复核', time: '09-09 17:31', tone: 'warn' },
]
</script>

<style scoped>
.settings-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr);
  gap: 16px;
  align-items: start;
}
.settings-main,
.settings-side {
  display: grid;
  gap: 16px;
}
.account-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
}
.account-meta {
  flex: 1;
  min-width: 0;
}
.account-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--qz-ink);
}
.account-sub {
  margin-top: 5px;
  font-size: 12px;
  color: var(--qz-muted);
}
.account-tags {
  margin-top: 10px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.capability-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 0 20px 20px;
}
.capability-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 15px;
  border: 1px solid var(--qz-line);
  border-radius: 12px;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}
.capability-card:hover {
  border-color: var(--qz-primary-line);
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(28, 26, 60, 0.06);
}
.capability-meta {
  flex: 1;
  min-width: 0;
}
.capability-title {
  font-size: 13.5px;
  font-weight: 650;
  color: var(--qz-ink);
}
.capability-desc {
  margin-top: 5px;
  font-size: 11.5px;
  color: var(--qz-muted);
  line-height: 1.55;
}
.capability-arrow {
  color: #c3c7d8;
  font-size: 13px;
  margin-top: 3px;
}
.switch-list {
  padding: 0 20px 8px;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 0;
  border-top: 1px solid var(--qz-line);
}
.switch-row:first-child {
  border-top: 0;
}
.switch-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink);
}
.switch-desc {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--qz-muted);
}
.audit-list {
  padding: 0 20px 14px;
}
.audit-row {
  display: flex;
  gap: 9px;
  padding: 10px 0;
  border-bottom: 1px dashed var(--qz-line);
}
.audit-row:last-child {
  border-bottom: 0;
}
.audit-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}
.audit-dot--primary {
  background: var(--qz-primary);
}
.audit-dot--success {
  background: var(--qz-success);
}
.audit-dot--info {
  background: var(--qz-info);
}
.audit-dot--warn {
  background: var(--qz-warn);
}
.audit-title {
  font-size: 12.5px;
  color: var(--qz-ink-2);
  line-height: 1.5;
}
.audit-time {
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--qz-muted);
}
.usage-card {
  padding: 18px 20px 20px;
}
.usage-value {
  margin: 12px 0 10px;
  font-size: 24px;
  font-weight: 700;
  color: var(--qz-ink);
}
.usage-value span {
  font-size: 12px;
  font-weight: 500;
  color: var(--qz-muted);
}
.usage-tip {
  margin: 12px 0 14px;
  font-size: 11.5px;
  color: var(--qz-muted);
  line-height: 1.6;
}

@media (max-width: 1180px) {
  .settings-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .capability-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
