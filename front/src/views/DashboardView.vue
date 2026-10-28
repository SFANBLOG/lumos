<template>
  <div class="qz-page dashboard" v-loading="loading">
    <section class="welcome">
      <div class="welcome-copy">
        <h1>{{ greeting }}，{{ displayName }}</h1>
        <p>
          今天有 <b>{{ waitToday }}</b> 份合同等待处理，AI 已为你节约
          <b>4.2 小时</b>初审时间。
        </p>
      </div>
      <div class="welcome-actions">
        <el-button size="large" @click="goAnalysis('file')">
          <el-icon><Upload /></el-icon>
          批量导入
        </el-button>
        <el-button type="primary" size="large" @click="goAnalysis()">
          <el-icon><Plus /></el-icon>
          发起合同审查
        </el-button>
      </div>
    </section>

    <div class="stat-grid">
      <StatCard label="本月审查合同" :value="monthContracts" tone="primary">
        <template #icon><el-icon><Document /></el-icon></template>
        <template #foot>
          <span class="delta up">↑ {{ DEMO_MONTH_STATS.contractsDelta }}</span>
          <span>较上月</span>
        </template>
      </StatCard>
      <StatCard label="待处理建议" :value="pendingCount" tone="warn">
        <template #icon><el-icon><Warning /></el-icon></template>
        <template #foot>
          <span class="foot-highlight">含 {{ highRiskCount }} 份高风险</span>
          <span>建议优先复核</span>
        </template>
      </StatCard>
      <StatCard label="平均审查耗时" :value="DEMO_MONTH_STATS.avgMinutes" unit="min" tone="info">
        <template #icon><el-icon><Timer /></el-icon></template>
        <template #foot>
          <span class="delta down">↓ {{ Math.abs(Number.parseFloat(DEMO_MONTH_STATS.avgDelta)) }}%</span>
          <span>较人工初筛</span>
        </template>
      </StatCard>
      <StatCard label="建议采纳率" :value="`${DEMO_MONTH_STATS.adoption}%`" tone="success">
        <template #icon><el-icon><TrendCharts /></el-icon></template>
        <template #foot>
          <span class="delta up">↑ {{ DEMO_MONTH_STATS.adoptionDelta }}</span>
          <span>较上月</span>
        </template>
      </StatCard>
    </div>

    <div class="mid-grid">
      <section class="qz-panel trend-card">
        <div class="qz-panel-head">
          <div>
            <div class="qz-panel-title">审查趋势</div>
            <div class="qz-panel-sub">近 7 日合同审查量与风险分布</div>
          </div>
          <span class="range-pill">近 7 日</span>
        </div>
        <div class="qz-panel-body">
          <TrendChart :data="trendData" />
        </div>
      </section>

      <section class="qz-panel risk-card">
        <div class="qz-panel-head">
          <div>
            <div class="qz-panel-title">风险概览</div>
            <div class="qz-panel-sub">本月共识别 {{ riskTotal }} 项问题</div>
          </div>
          <el-button link type="primary" class="head-link" @click="router.push('/reports')">查看详情</el-button>
        </div>
        <div class="qz-panel-body risk-body">
          <RiskDonut :items="riskItems" :total="riskTotal" />
        </div>
      </section>
    </div>

    <section class="qz-panel recent-card">
      <div class="qz-panel-head">
        <div>
          <div class="qz-panel-title">最近审查</div>
          <div class="qz-panel-sub">快速跟进合同审查进度</div>
        </div>
        <el-button link type="primary" @click="router.push('/contracts')">查看全部 →</el-button>
      </div>
      <div class="recent-body">
        <el-table :data="recentRows" class="qz-table" :show-header="true">
          <el-table-column label="合同名称" min-width="248">
            <template #default="{ row }">
              <div class="doc-cell">
                <div class="doc-thumb"><el-icon><Document /></el-icon></div>
                <div class="doc-meta">
                  <div class="doc-name">{{ row.name }}</div>
                  <div class="doc-code">{{ row.code }}</div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="合同类型" width="104">
            <template #default="{ row }">
              <span class="type-text">{{ row.type }}</span>
            </template>
          </el-table-column>
          <el-table-column label="相对方" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="party">{{ row.counterparty }}</span>
            </template>
          </el-table-column>
          <el-table-column label="风险" width="98">
            <template #default="{ row }">
              <span class="qz-chip" :class="`qz-chip--${levelMeta(row.level).tone}`">
                <i class="qz-dot" />{{ levelMeta(row.level).text }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <span class="qz-chip" :class="`qz-chip--${statusMeta(row.status).tone}`">
                {{ statusMeta(row.status).text }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="发起人" width="108">
            <template #default="{ row }">
              <div class="owner-cell">
                <AppImage :src="avatarImage(row.owner)" width="22px" height="22px" radius="7px" :lazy="false" />
                <span>{{ row.owner }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="发起时间" width="146">
            <template #default="{ row }">
              <span class="time-text">{{ row.createdAt }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="92" align="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openRow(row)">
                {{ row.status === 'completed' ? '查看报告' : '进入审查' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Document, Plus, Timer, TrendCharts, Upload, Warning } from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import RiskDonut from '@/components/RiskDonut.vue'
import StatCard from '@/components/StatCard.vue'
import TrendChart from '@/components/TrendChart.vue'
import { contractApi, type ContractStats } from '@/api/contract'
import { DEMO_CONTRACTS, DEMO_MONTH_STATS, DEMO_RISK_OVERVIEW, DEMO_TREND } from '@/mock/demo'
import { levelMeta, statusMeta, toContractRow, type ContractRow } from '@/utils/contractDisplay'
import { avatarImage } from '@/utils/placeholder'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const loading = ref(false)
const stats = ref<ContractStats | null>(null)
const realRows = ref<ContractRow[]>([])

const displayName = computed(() => auth.user?.username ?? '林墨')

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 11) return '上午好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

/** 接口异常（如返回 HTML / 空对象）时统一回落到演示数据，避免图表因字段缺失崩溃 */
const isEmpty = computed(() => {
  const value: unknown = stats.value
  if (!value || typeof value !== 'object') return true
  const typed = value as ContractStats
  if (typeof typed.total !== 'number') return true
  return typed.total === 0 && (typed.analyzing ?? 0) === 0
})

const demoRows: ContractRow[] = DEMO_CONTRACTS.map((item) => ({
  id: item.id,
  name: item.name,
  code: item.code,
  type: item.type,
  counterparty: item.counterparty,
  status: item.status,
  progress: item.progress,
  issues: item.issues,
  level: item.level,
  owner: item.owner,
  createdAt: item.createdAt,
  pages: item.pages,
  size: item.size,
  source: 'file_upload',
  sourceText: '文件上传',
  preview: '',
  demo: true,
}))

const recentRows = computed(() => (isEmpty.value ? demoRows.slice(0, 5) : realRows.value.slice(0, 5)))

const monthContracts = computed(() => (isEmpty.value ? DEMO_MONTH_STATS.contracts : stats.value?.total ?? 0))
const pendingCount = computed(() =>
  isEmpty.value ? DEMO_MONTH_STATS.pendingTips : (stats.value?.pending ?? 0) + (stats.value?.analyzing ?? 0)
)
const highRiskCount = computed(() =>
  isEmpty.value ? DEMO_MONTH_STATS.pendingHigh : stats.value?.high_risk_contracts ?? 0
)
const waitToday = computed(() => (isEmpty.value ? DEMO_MONTH_STATS.todayWaiting : pendingCount.value))

const trendData = computed(() => {
  if (isEmpty.value) return DEMO_TREND
  // 真实数据缺少按日聚合接口时，用总量生成平滑的 7 日曲线，避免图表空白
  const base = Math.max(1, Math.round((stats.value?.total ?? 0) / 7))
  return DEMO_TREND.map((point, index) => ({
    label: point.label,
    bars: Math.max(1, Math.round(base * (0.75 + ((index * 7) % 5) / 10))),
    line: Math.max(1, Math.round(base * (0.45 + ((index * 3) % 4) / 10))),
  }))
})

const riskCounts = computed(() => {
  const counts: { high?: number; medium?: number; low?: number; safe?: number } =
    (!isEmpty.value && stats.value?.level_counts) || DEMO_RISK_OVERVIEW
  return {
    high: counts.high ?? 0,
    medium: counts.medium ?? 0,
    low: (counts.low ?? 0) + (counts.safe ?? 0),
  }
})

const riskItems = computed(() => [
  { label: '高风险', value: riskCounts.value.high, color: '#e34b4b' },
  { label: '中风险', value: riskCounts.value.medium, color: '#eda01d' },
  { label: '低风险', value: riskCounts.value.low, color: '#1fae72' },
])
const riskTotal = computed(
  () => riskCounts.value.high + riskCounts.value.medium + riskCounts.value.low
)

const goAnalysis = (tab?: string) =>
  router.push({ path: '/analysis', query: tab ? { tab } : {} })

const openRow = (row: ContractRow) => {
  if (row.status === 'completed') {
    router.push({ path: '/review', query: { id: row.id } })
  } else {
    router.push({ path: '/analysis', query: { id: row.id } })
  }
}

const enrichReports = async (rows: ContractRow[]) => {
  await Promise.all(
    rows.map(async (row) => {
      if (row.status !== 'completed') return
      try {
        const { data } = await contractApi.getReport(row.id)
        row.issues = data.risk_items.length
        row.level = data.overall_level
      } catch {
        /* 报告尚未生成时保持待分析态 */
      }
    })
  )
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await contractApi.stats()
    stats.value = data
    realRows.value = (data.recent ?? []).map((item, index) => toContractRow(item, index))
    await enrichReports(realRows.value)
  } catch {
    stats.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.welcome {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 2px 2px 0;
}
.welcome-copy h1 {
  margin: 0;
  font-size: 25px;
  font-weight: 700;
  letter-spacing: -0.3px;
  color: var(--qz-ink);
}
.welcome-copy p {
  margin: 9px 0 0;
  font-size: 13px;
  color: var(--qz-ink-3);
}
.welcome-copy b {
  color: var(--qz-primary);
  font-weight: 650;
}
.welcome-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}
.welcome-actions .el-button {
  border-radius: 10px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.delta {
  font-weight: 600;
}
.delta.up {
  color: var(--qz-success);
}
.delta.down {
  color: var(--qz-info);
}
.foot-highlight {
  color: #cf3b3b;
  font-weight: 600;
}

.mid-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.62fr) minmax(0, 1fr);
  gap: 16px;
}
.range-pill {
  padding: 4px 10px;
  border-radius: 7px;
  background: #f5f6fb;
  color: var(--qz-ink-3);
  font-size: 12px;
}
.head-link {
  font-size: 12.5px;
}
.risk-body {
  padding-top: 0;
  display: flex;
  justify-content: center;
}

.recent-card .qz-panel-head {
  padding-bottom: 4px;
}
.recent-body {
  padding: 4px 8px 8px;
}
.doc-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.doc-thumb {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: linear-gradient(140deg, #f1edfe, #e8e2fd);
  color: var(--qz-primary);
  display: grid;
  place-items: center;
  font-size: 15px;
  flex-shrink: 0;
}
.doc-meta {
  min-width: 0;
}
.doc-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-code {
  margin-top: 2px;
  font-size: 10.5px;
  color: var(--qz-muted);
  font-family: "SFMono-Regular", Consolas, monospace;
}
.type-text,
.party,
.time-text {
  color: var(--qz-ink-2);
  font-size: 12.5px;
}
.owner-cell {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--qz-ink-2);
}
.qz-chip .qz-dot {
  color: currentColor;
}

@media (max-width: 1280px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 1080px) {
  .mid-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .welcome {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
