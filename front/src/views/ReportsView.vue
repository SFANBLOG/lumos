<template>
  <div class="qz-page">
    <PageHeader title="审查报告" description="查看、归档并导出已完成的合同审查报告。">
      <template #actions>
        <el-button @click="exportSummary">
          <el-icon><Download /></el-icon>
          批量下载
        </el-button>
      </template>
    </PageHeader>

    <div class="stat-grid">
      <StatCard label="本月完成报告" :value="monthlyReports" tone="primary">
        <template #icon><el-icon><DocumentChecked /></el-icon></template>
        <template #foot><span class="delta up">↑ 12.4%</span><span>较上月</span></template>
      </StatCard>
      <StatCard label="平均处理时长" :value="DEMO_REPORT_STATS.avgMinutes" unit="分钟" tone="info">
        <template #icon><el-icon><Timer /></el-icon></template>
        <template #foot><span>含 AI 初审与人工复核</span></template>
      </StatCard>
      <StatCard label="问题解决率" :value="`${DEMO_REPORT_STATS.resolveRate}%`" tone="success">
        <template #icon><el-icon><CircleCheck /></el-icon></template>
        <template #foot><span class="delta up">↑ 3.6%</span><span>较上月</span></template>
      </StatCard>
    </div>

    <section class="qz-panel">
      <div class="filters">
        <el-input
          v-model="keyword"
          class="filter-search"
          placeholder="搜索报告编号或合同名称"
          :prefix-icon="Search"
          clearable
        />
        <el-select v-model="levelFilter" class="filter-select" placeholder="风险等级" clearable>
          <el-option label="高风险" value="high" />
          <el-option label="中风险" value="medium" />
          <el-option label="低风险" value="low" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          class="filter-date"
          type="daterange"
          range-separator="至"
          start-placeholder="完成时间"
          end-placeholder="结束时间"
          value-format="YYYY-MM-DD"
        />
        <span class="filter-total">
          共 {{ filteredRows.length }} 份报告
          <template v-if="isDemo"> · 演示数据</template>
        </span>
      </div>

      <el-table :data="pagedRows" class="qz-table" empty-text="暂无已完成报告" v-loading="loading">
        <el-table-column label="报告编号" width="168">
          <template #default="{ row }">
            <span class="report-code">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同名称" min-width="268">
          <template #default="{ row }">
            <div class="doc-cell">
              <div class="doc-thumb"><el-icon><Document /></el-icon></div>
              <div class="doc-meta">
                <div class="doc-name">{{ row.contractName }}</div>
                <div class="doc-code">AI 初审判定 · 人工已复核</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="整体风险" width="118">
          <template #default="{ row }">
            <span class="qz-chip" :class="`qz-chip--${levelMeta(row.level).tone}`">
              <i v-if="row.level !== 'none'" class="qz-dot" />{{ levelMeta(row.level).text }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="问题数量" width="102" align="center">
          <template #default="{ row }">
            <span v-if="row.issues" class="issue-count">{{ row.issues }} 项</span>
            <span v-else class="qz-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发起人" width="106">
          <template #default="{ row }">
            <div class="owner-cell">
              <AppImage :src="avatarImage(row.owner)" width="22px" height="22px" radius="7px" :lazy="false" />
              <span>{{ row.owner }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="完成时间" width="152">
          <template #default="{ row }">
            <span class="time-text">{{ row.finishedAt }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="132" align="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button link type="primary" @click="openReport(row)">查看报告</el-button>
              <button class="download-btn" title="下载报告" @click="downloadReport(row)">
                <el-icon><Download /></el-icon>
              </button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-footer">
        <span class="qz-muted">共 {{ filteredRows.length }} 份报告</span>
        <el-pagination
          v-model:current-page="page"
          background
          layout="prev, pager, next"
          :page-size="pageSize"
          :total="filteredRows.length"
        />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  Document,
  DocumentChecked,
  Download,
  Search,
  Timer,
} from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatCard from '@/components/StatCard.vue'
import { contractApi } from '@/api/contract'
import { DEMO_REPORTS, DEMO_REPORT_STATS } from '@/mock/demo'
import { formatTime } from '@/utils/contractMeta'
import { levelMeta, toContractRow } from '@/utils/contractDisplay'
import { avatarImage } from '@/utils/placeholder'

interface ReportRow {
  id: string
  code: string
  contractName: string
  level: string
  issues: number
  owner: string
  finishedAt: string
  demo: boolean
}

const route = useRoute()
const router = useRouter()

const rows = ref<ReportRow[]>([])
const loading = ref(false)
const isDemo = ref(false)
const keyword = ref('')
const levelFilter = ref('')
const dateRange = ref<[string, string] | null>(null)
const page = ref(1)
const pageSize = 8
const monthlyReports = ref(DEMO_REPORT_STATS.monthly)

const filteredRows = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return rows.value.filter((row) => {
    if (levelFilter.value && row.level !== levelFilter.value) return false
    if (dateRange.value) {
      const day = row.finishedAt.slice(0, 10)
      if (day < dateRange.value[0] || day > dateRange.value[1]) return false
    }
    if (!query) return true
    return row.code.toLowerCase().includes(query) || row.contractName.toLowerCase().includes(query)
  })
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize
  return filteredRows.value.slice(start, start + pageSize)
})

const openReport = (row: ReportRow) => {
  router.push({ path: '/review', query: { id: row.id, from: 'reports' } })
}

const buildReportText = (row: ReportRow, report?: { summary: string; risk_items: Array<Record<string, string>> }) => {
  const header = [
    `审查报告 ${row.code}`,
    `合同名称：${row.contractName}`,
    `整体风险：${levelMeta(row.level).text}`,
    `问题数量：${row.issues} 项`,
    `发起人：${row.owner}`,
    `完成时间：${row.finishedAt}`,
    '',
  ]
  if (!report) {
    header.push('（报告正文尚未生成，可在审查详情中重新获取）')
    return header.join('\n')
  }
  header.push(`审查结论：${report.summary}`, '')
  report.risk_items.forEach((risk, index) => {
    header.push(
      `${index + 1}. [${risk.level}] ${risk.title}`,
      `   原文：${risk.original_clause || '—'}`,
      `   解读：${risk.explanation || '—'}`,
      `   依据：${risk.legal_basis || '—'}`,
      `   建议：${risk.negotiation_tip || '—'}`,
      ''
    )
  })
  return header.join('\n')
}

const saveText = (filename: string, content: string) => {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

const downloadReport = async (row: ReportRow) => {
  if (row.demo) {
    saveText(`${row.code}.txt`, buildReportText(row))
    ElMessage.success('已导出示例报告')
    return
  }
  try {
    const { data } = await contractApi.getReport(row.id)
    saveText(
      `${row.code}.txt`,
      buildReportText(row, { summary: data.summary, risk_items: data.risk_items as unknown as Array<Record<string, string>> })
    )
    ElMessage.success('报告已导出')
  } catch {
    saveText(`${row.code}.txt`, buildReportText(row))
    ElMessage.warning('报告正文暂不可用，已导出报告摘要')
  }
}

const exportSummary = () => {
  const header = ['报告编号', '合同名称', '整体风险', '问题数量', '发起人', '完成时间']
  const lines = filteredRows.value.map((row) => [
    row.code,
    row.contractName,
    levelMeta(row.level).text,
    String(row.issues),
    row.owner,
    row.finishedAt,
  ])
  const csv = [header, ...lines]
    .map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\r\n')
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `审查报告清单-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
  ElMessage.success(`已导出 ${filteredRows.value.length} 份报告清单`)
}

const demoRows: ReportRow[] = DEMO_REPORTS.map((item) => ({
  id: item.contractId,
  code: item.code,
  contractName: item.contractName,
  level: item.level,
  issues: item.issues,
  owner: item.owner,
  finishedAt: item.finishedAt,
  demo: true,
}))

const fetchReports = async () => {
  loading.value = true
  try {
    const { data } = await contractApi.list({ page: 1, page_size: 50, status: 'completed' })
    if (!Array.isArray(data.items) || !data.items.length) {
      rows.value = demoRows
      isDemo.value = true
      return
    }
    const mapped: ReportRow[] = data.items.map((item, index) => {
      const contract = toContractRow(item, index)
      const day = (item.created_at || '').slice(0, 10).replace(/-/g, '')
      return {
        id: item.id,
        code: `RPT-${day}-${String(index + 1).padStart(3, '0')}`,
        contractName: contract.name,
        level: 'none',
        issues: 0,
        owner: contract.owner,
        finishedAt: formatTime(item.created_at),
        demo: false,
      }
    })
    rows.value = mapped
    isDemo.value = false
    monthlyReports.value = data.total
    await Promise.all(
      mapped.map(async (row) => {
        try {
          const { data: report } = await contractApi.getReport(row.id)
          row.level = report.overall_level
          row.issues = report.risk_items.length
        } catch {
          /* 报告缺失时保留待分析态 */
        }
      })
    )
  } catch {
    rows.value = demoRows
    isDemo.value = true
  } finally {
    loading.value = false
  }
}

watch([keyword, levelFilter, dateRange], () => {
  page.value = 1
})

watch(
  () => route.query.open,
  (open) => {
    if (typeof open === 'string' && open) {
      router.replace({ path: '/review', query: { id: open, from: 'reports' } })
    }
  }
)

onMounted(fetchReports)
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.delta {
  font-weight: 600;
}
.delta.up {
  color: var(--qz-success);
}
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px;
  flex-wrap: wrap;
}
.filter-search {
  width: 300px;
}
.filter-select {
  width: 132px;
}
.filter-date {
  width: 256px !important;
}
.filter-total {
  margin-left: auto;
  font-size: 12px;
  color: var(--qz-muted);
}
.report-code {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  color: var(--qz-ink-2);
}
.doc-cell {
  display: flex;
  align-items: center;
  gap: 11px;
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
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--qz-muted);
}
.issue-count {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--qz-ink-2);
}
.owner-cell {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--qz-ink-2);
}
.time-text {
  font-size: 12.5px;
  color: var(--qz-ink-3);
  font-variant-numeric: tabular-nums;
}
.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}
.download-btn {
  width: 24px;
  height: 24px;
  border: 1px solid var(--qz-line);
  border-radius: 7px;
  background: #ffffff;
  color: var(--qz-ink-3);
  display: grid;
  place-items: center;
  cursor: pointer;
  font-size: 12px;
}
.download-btn:hover {
  color: var(--qz-primary);
  border-color: var(--qz-primary-line);
  background: var(--qz-primary-soft);
}
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--qz-line);
  margin-top: 6px;
}

@media (max-width: 1180px) {
  .stat-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
