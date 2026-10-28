<template>
  <div class="qz-page">
    <PageHeader
      title="合同管理"
      description="集中管理合同文件、审查进度与历史版本。"
    >
      <template #actions>
        <el-button @click="exportCsv">
          <el-icon><Download /></el-icon>
          导出清单
        </el-button>
        <el-button type="primary" @click="router.push('/analysis')">
          <el-icon><Plus /></el-icon>
          发起审查
        </el-button>
      </template>
    </PageHeader>

    <section class="qz-panel">
      <div class="status-tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="status-tab"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
          <span class="tab-count">{{ tabCount(tab.key) }}</span>
        </button>
      </div>

      <div class="filters">
        <el-input
          v-model="keyword"
          class="filter-search"
          placeholder="搜索合同名称、编号或相对方"
          :prefix-icon="Search"
          clearable
        />
        <el-select v-model="typeFilter" class="filter-select" placeholder="合同类型" clearable>
          <el-option v-for="type in TYPES" :key="type" :label="type" :value="type" />
        </el-select>
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
          start-placeholder="发起时间"
          end-placeholder="结束时间"
          value-format="YYYY-MM-DD"
          :clearable="true"
        />
        <el-button class="filter-reset" :icon="RefreshLeft" circle title="重置筛选" @click="resetFilters" />
        <span class="filter-total">
          共 {{ filteredRows.length }} 条记录
          <template v-if="rowSourceIsDemo"> · 演示数据</template>
        </span>
      </div>

      <el-table
        :data="pagedRows"
        class="qz-table contracts-table"
        :empty-text="emptyText"
        v-loading="loading"
        @row-dblclick="openRow"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column label="合同信息" min-width="238">
          <template #default="{ row }">
            <div class="doc-cell">
              <div class="doc-thumb" :style="{ background: thumbStyle(row.name) }">{{ row.name.slice(0, 1) }}</div>
              <div class="doc-meta">
                <div class="doc-name">{{ row.name }}</div>
                <div class="doc-code">{{ row.code }} · {{ row.type }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="相对方" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.counterparty }}</template>
        </el-table-column>
        <el-table-column label="审查进度" width="118">
          <template #default="{ row }">
            <div v-if="row.status === 'analyzing'" class="progress-cell">
              <el-progress
                :percentage="row.progress"
                :stroke-width="4"
                :show-text="false"
                color="#6c4cf1"
                class="mini-progress"
              />
              <span>{{ row.progress }}%</span>
            </div>
            <span v-else class="qz-chip" :class="`qz-chip--${statusMeta(row.status).tone}`">
              {{ statusMeta(row.status).text }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="问题数" width="76" align="center">
          <template #default="{ row }">
            <span v-if="row.issues > 0" class="issue-count" :class="{ danger: row.level === 'high' }">{{ row.issues }}</span>
            <span v-else class="qz-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="104">
          <template #default="{ row }">
            <span class="qz-chip" :class="`qz-chip--${levelMeta(row.level).tone}`">
              <i v-if="row.level !== 'none'" class="qz-dot" />{{ levelMeta(row.level).text }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="发起人" width="92">
          <template #default="{ row }">
            <div class="owner-cell">
              <AppImage :src="avatarImage(row.owner)" width="22px" height="22px" radius="7px" :lazy="false" />
              <span>{{ row.owner }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="发起时间" width="136">
          <template #default="{ row }">
            <span class="time-text">{{ row.createdAt }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="108" align="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button link type="primary" @click="openRow(row)">
                {{ row.status === 'completed' ? '查看报告' : '进入审查' }}
              </el-button>
              <el-dropdown trigger="click" @command="(command: string) => onRowCommand(command, row)">
                <button class="more-btn" title="更多操作">
                  <el-icon><MoreFilled /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="open">打开审查详情</el-dropdown-item>
                    <el-dropdown-item command="rerun">重新审查</el-dropdown-item>
                    <el-dropdown-item command="copy">复制合同编号</el-dropdown-item>
                    <el-dropdown-item command="download" divided>下载审查报告</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-footer">
        <span class="qz-muted">
          共 {{ filteredRows.length }} 条记录
          <template v-if="rowSourceIsDemo"> · 演示数据</template>
        </span>
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
import { Download, MoreFilled, Plus, RefreshLeft, Search } from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import PageHeader from '@/components/PageHeader.vue'
import { contractApi } from '@/api/contract'
import { DEMO_CONTRACTS } from '@/mock/demo'
import {
  levelMeta,
  statusMeta,
  toContractRow,
  type ContractRow,
} from '@/utils/contractDisplay'
import { avatarImage } from '@/utils/placeholder'

const router = useRouter()
const route = useRoute()

const TABS = [
  { key: 'all', label: '全部合同' },
  { key: 'pending', label: '待处理' },
  { key: 'analyzing', label: '审查中' },
  { key: 'reviewing', label: '待复核' },
  { key: 'completed', label: '已完成' },
]
const TYPES = ['采购合同', '服务合同', '技术合同', '租赁合同', '保密协议', '销售合同', '劳动合同']
const THUMB_COLORS = [
  'linear-gradient(140deg,#efeafd,#e2d9fd)',
  'linear-gradient(140deg,#e8f1ff,#d8e6ff)',
  'linear-gradient(140deg,#e9f8f1,#d5f2e4)',
  'linear-gradient(140deg,#fdf3e3,#fbe6c6)',
]

const rows = ref<ContractRow[]>([])
const loading = ref(false)
const activeTab = ref('all')
const keyword = ref('')
const typeFilter = ref('')
const levelFilter = ref('')
const dateRange = ref<[string, string] | null>(null)
const page = ref(1)
const pageSize = 8

const rowSourceIsDemo = ref(false)
const emptyText = computed(() =>
  rowSourceIsDemo.value ? '演示数据：后端暂未返回合同记录' : '暂无合同，点击右上角「发起审查」上传第一份文件'
)

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

const tabCount = (key: string) => {
  if (key === 'all') return rows.value.length
  if (key === 'pending') return rows.value.filter((row) => row.status === 'pending').length
  if (key === 'analyzing') return rows.value.filter((row) => row.status === 'analyzing').length
  if (key === 'reviewing') return rows.value.filter((row) => row.status === 'reviewing').length
  return rows.value.filter((row) => row.status === 'completed').length
}

const filteredRows = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return rows.value.filter((row) => {
    if (activeTab.value !== 'all' && row.status !== activeTab.value) return false
    if (typeFilter.value && row.type !== typeFilter.value) return false
    if (levelFilter.value && row.level !== levelFilter.value) return false
    if (dateRange.value) {
      const day = row.createdAt.slice(0, 10)
      if (day < dateRange.value[0] || day > dateRange.value[1]) return false
    }
    if (!query) return true
    return (
      row.name.toLowerCase().includes(query) ||
      row.code.toLowerCase().includes(query) ||
      row.counterparty.toLowerCase().includes(query)
    )
  })
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize
  return filteredRows.value.slice(start, start + pageSize)
})

const thumbStyle = (name: string) => {
  const index = name.charCodeAt(0) % THUMB_COLORS.length
  return THUMB_COLORS[index]
}

const switchTab = (key: string) => {
  activeTab.value = key
  page.value = 1
}

const resetFilters = () => {
  keyword.value = ''
  typeFilter.value = ''
  levelFilter.value = ''
  dateRange.value = null
  activeTab.value = 'all'
  page.value = 1
}

const openRow = (row: ContractRow) => {
  router.push({ path: '/review', query: { id: row.id } })
}

const onRowCommand = async (command: string, row: ContractRow) => {
  if (command === 'copy') {
    try {
      await navigator.clipboard.writeText(row.code)
      ElMessage.success('合同编号已复制')
    } catch {
      ElMessage.warning('当前浏览器不支持自动复制')
    }
    return
  }
  if (command === 'rerun') {
    router.push({ path: '/analysis', query: { id: row.id } })
    return
  }
  if (command === 'download') {
    router.push({ path: '/review', query: { id: row.id, download: '1' } })
    return
  }
  openRow(row)
}

const exportCsv = () => {
  const header = ['合同名称', '合同编号', '合同类型', '相对方', '状态', '风险等级', '问题数', '发起人', '发起时间']
  const lines = filteredRows.value.map((row) => [
    row.name,
    row.code,
    row.type,
    row.counterparty,
    statusMeta(row.status).text,
    levelMeta(row.level).text,
    String(row.issues),
    row.owner,
    row.createdAt,
  ])
  const csv = [header, ...lines]
    .map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\r\n')
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `合同清单-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(link.href)
  ElMessage.success(`已导出 ${filteredRows.value.length} 条合同记录`)
}

const fetchRows = async () => {
  loading.value = true
  try {
    const { data } = await contractApi.list({ page: 1, page_size: 100 })
    if (Array.isArray(data.items) && data.items.length) {
      rows.value = data.items.map((item, index) => toContractRow(item, index))
      rowSourceIsDemo.value = false
    } else {
      rows.value = demoRows
      rowSourceIsDemo.value = true
    }
  } catch {
    rows.value = demoRows
    rowSourceIsDemo.value = true
  } finally {
    loading.value = false
  }
}

watch([keyword, activeTab, typeFilter, levelFilter, dateRange], () => {
  page.value = 1
})

watch(
  () => route.query.q,
  (query) => {
    if (typeof query === 'string') keyword.value = query
  },
  { immediate: true }
)

onMounted(fetchRows)
</script>

<style scoped>
.status-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 18px 0;
  border-bottom: 1px solid var(--qz-line);
  overflow-x: auto;
}
.status-tab {
  position: relative;
  padding: 4px 12px 14px;
  border: 0;
  background: transparent;
  color: var(--qz-ink-3);
  font-size: 13.5px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.18s ease;
}
.status-tab:hover {
  color: var(--qz-ink);
}
.status-tab.active {
  color: var(--qz-ink);
  font-weight: 600;
}
.status-tab.active::after {
  content: "";
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: -1px;
  height: 2px;
  border-radius: 2px;
  background: var(--qz-primary);
}
.tab-count {
  margin-left: 5px;
  font-size: 11.5px;
  color: var(--qz-muted);
}
.status-tab.active .tab-count {
  color: var(--qz-primary);
}

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px;
  flex-wrap: wrap;
}
.filter-search {
  width: 268px;
}
.filter-select {
  width: 132px;
}
.filter-date {
  width: 250px !important;
}
.filter-reset {
  color: var(--qz-ink-3);
}
.filter-total {
  margin-left: auto;
  font-size: 12px;
  color: var(--qz-muted);
}

.contracts-table {
  padding: 0 6px;
}
.doc-cell {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}
.doc-thumb {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 650;
  color: #5a3ade;
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
.progress-cell {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11.5px;
  color: var(--qz-primary);
}
.mini-progress {
  flex: 1;
  min-width: 0;
}
.issue-count {
  font-size: 13px;
  font-weight: 650;
  color: var(--qz-ink);
}
.issue-count.danger {
  color: #cf3b3b;
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
  gap: 2px;
}
.more-btn {
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--qz-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.more-btn:hover {
  background: #f2f3f9;
  color: var(--qz-ink-2);
}
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--qz-line);
  margin-top: 6px;
}
</style>
