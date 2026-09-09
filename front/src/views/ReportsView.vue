<template>
  <div class="reports">
    <el-card shadow="never">
      <div class="filter-bar">
        <el-radio-group v-model="statusFilter" @change="onFilterChange">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="analyzing">进行中</el-radio-button>
          <el-radio-button value="completed">已完成</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
        <el-button :icon="Refresh" circle plain @click="fetchList" />
      </div>

      <el-table :data="items" v-loading="loading" empty-text="暂无合同记录">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="sourceTagType(row.source)">{{ sourceLabel(row.source) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="preview" label="正文预览" show-overflow-tooltip />
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              :disabled="row.status !== 'completed'"
              :loading="openingId === row.id"
              @click="openReport(row.id)"
            >
              {{ row.status === 'completed' ? '查看报告' : statusLabel(row.status) }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="onPageChange"
        />
      </div>
    </el-card>

    <!-- 报告抽屉 -->
    <el-drawer v-model="drawerVisible" size="560px" :title="`分析报告 · ${report?.contract_id.slice(0, 8)}`">
      <div v-if="report" class="report" v-loading="reportLoading">
        <div class="score-area">
          <div
            class="score-ring"
            :style="{ borderColor: levelColor(report.overall_level) }"
          >
            <div class="score-num">{{ report.overall_score }}</div>
            <div class="score-cap">安全分</div>
          </div>
          <div class="score-side">
            <el-tag size="large" :type="levelTagType(report.overall_level)">
              {{ levelLabel(report.overall_level) }}
            </el-tag>
            <div class="summary">{{ report.summary }}</div>
            <div class="analyzed-at">分析时间：{{ formatTime(report.analyzed_at) }}</div>
          </div>
        </div>

        <el-divider content-position="left">风险条目 ({{ report.risk_items.length }})</el-divider>
        <div v-if="!report.risk_items.length" class="no-risk">✅ 未发现明显风险条款</div>
        <el-collapse v-else>
          <el-collapse-item v-for="(risk, idx) in report.risk_items" :key="idx">
            <template #title>
              <div class="risk-title">
                <el-tag size="small" :type="levelTagType(risk.level)">{{ levelLabel(risk.level) }}</el-tag>
                <el-tag size="small" type="info" effect="plain">{{ categoryLabel(risk.category) }}</el-tag>
                <span class="risk-name">{{ risk.title }}</span>
              </div>
            </template>
            <div class="risk-body">
              <p v-if="risk.original_clause"><strong>原始条文：</strong>{{ risk.original_clause }}</p>
              <p><strong>解读：</strong>{{ risk.explanation }}</p>
              <p v-if="risk.legal_basis"><strong>法律依据：</strong>{{ risk.legal_basis }}</p>
              <p><strong>谈判建议：</strong>{{ risk.negotiation_tip }}</p>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { contractApi, type AnalysisReport, type ContractListItem } from '@/api/contract'
import {
  categoryLabel,
  formatTime,
  levelColor,
  levelLabel,
  levelTagType,
  sourceLabel,
  sourceTagType,
  statusLabel,
  statusTagType,
} from '@/utils/contractMeta'

const route = useRoute()

const items = ref<ContractListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const statusFilter = ref('')
const loading = ref(false)

const drawerVisible = ref(false)
const reportLoading = ref(false)
const report = ref<AnalysisReport | null>(null)
const openingId = ref('')

const fetchList = async () => {
  loading.value = true
  try {
    const { data } = await contractApi.list({
      page: page.value,
      page_size: pageSize,
      status: statusFilter.value || undefined,
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

const onFilterChange = () => {
  page.value = 1
  fetchList()
}
const onPageChange = (p: number) => {
  page.value = p
  fetchList()
}

const openReport = async (contractId: string) => {
  openingId.value = contractId
  report.value = null
  drawerVisible.value = true
  reportLoading.value = true
  try {
    const { data } = await contractApi.getReport(contractId)
    report.value = data
  } catch (e: any) {
    drawerVisible.value = false
    ElMessage.error(e.response?.data?.detail || '报告获取失败')
  } finally {
    reportLoading.value = false
    openingId.value = ''
  }
}

// 支持 /reports?open=<id> 深链直达
watch(
  () => route.query.open,
  (open) => {
    if (typeof open === 'string' && open) {
      openReport(open)
    }
  },
  { immediate: true }
)

onMounted(fetchList)
</script>

<style scoped>
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.score-area {
  display: flex;
  gap: 20px;
  align-items: center;
}
.score-ring {
  width: 110px;
  height: 110px;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 6px solid #67c23a;
  flex-shrink: 0;
}
.score-num {
  font-size: 30px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
}
.score-cap {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.score-side {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.summary {
  color: #606266;
  font-size: 14px;
  line-height: 1.6;
}
.analyzed-at {
  font-size: 12px;
  color: #909399;
}
.no-risk {
  color: #67c23a;
  padding: 8px 0;
}
.risk-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.risk-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.risk-body p {
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
}
.risk-body p strong {
  color: #303133;
}
</style>
