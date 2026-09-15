<template>
  <div class="dashboard" v-loading="loading">
    <section class="hero">
      <div><span class="eyebrow">LUMOS AGENT OPERATIONS</span><h1>合同审查控制台</h1><p>将企业 Playbook、证据质检与人工审批置于同一条可审计工作流。</p></div>
      <div class="hero-actions"><el-button type="primary" size="large" @click="goAnalysis('file')">提交审查任务</el-button><el-button size="large" @click="goReports">进入合同库</el-button></div>
    </section>
    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value">{{ stats?.total ?? 0 }}</div>
          <div class="stat-label">累计分析</div>
          <div class="stat-extra">已完成 {{ stats?.completed ?? 0 }} 份</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value">{{ stats?.analyzing ?? 0 }}</div>
          <div class="stat-label">进行中</div>
          <div class="stat-extra">
            <el-button v-if="(stats?.analyzing ?? 0) > 0" link type="primary" size="small" @click="goReports">
              去看看 →
            </el-button>
            <span v-else>当前无任务</span>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value high">{{ stats?.high_risk_contracts ?? 0 }}</div>
          <div class="stat-label">高危合同</div>
          <div class="stat-extra">需重点复核</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-value">{{ stats?.avg_overall_score != null ? stats.avg_overall_score : '—' }}</div>
          <div class="stat-label">平均安全分</div>
          <div class="stat-extra">满分 100 分</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="ops-row">
      <el-col :span="15"><el-card shadow="never" class="pipeline"><template #header><div class="card-head"><span class="card-title">Agent 执行链路</span><el-tag type="success">实时可追溯</el-tag></div></template><div class="steps"><div><b>01</b><span>合同接入</span><small>文本 / 文档 / OCR</small></div><div><b>02</b><span>Playbook</span><small>企业审查标准</small></div><div><b>03</b><span>证据质检</span><small>原文与法条核验</small></div><div><b>04</b><span>人工复核</span><small>审批与审计</small></div></div></el-card></el-col>
      <el-col :span="9"><el-card shadow="never" class="review"><template #header><span class="card-title">待处理事项</span></template><div class="review-num">{{ stats?.high_risk_contracts ?? 0 }}</div><p>高风险合同等待人工复核</p><el-button link type="primary" @click="goReports">查看审查队列 →</el-button></el-card></el-col>
    </el-row>

    <!-- 快捷入口 -->
    <el-card shadow="never" class="quick-card">
      <template #header>
        <span class="card-title">快捷分析</span>
      </template>
      <div class="quick-actions">
        <div class="quick-item" @click="goAnalysis('text')">
          <el-icon class="qi-icon text"><EditPen /></el-icon>
          <div class="qi-name">粘贴文本</div>
          <div class="qi-desc">粘贴劳动合同全文</div>
        </div>
        <div class="quick-item" @click="goAnalysis('file')">
          <el-icon class="qi-icon file"><UploadFilled /></el-icon>
          <div class="qi-name">上传文件</div>
          <div class="qi-desc">PDF 等 9 种格式文档</div>
        </div>
        <div class="quick-item" @click="goAnalysis('url')">
          <el-icon class="qi-icon url"><Link /></el-icon>
          <div class="qi-name">网页链接</div>
          <div class="qi-desc">粘贴网站合同页面链接</div>
        </div>
        <div class="quick-item" @click="goConsult">
          <el-icon class="qi-icon consult"><ChatLineRound /></el-icon>
          <div class="qi-name">智能咨询</div>
          <div class="qi-desc">劳动法问答 · 法条引用</div>
        </div>
      </div>
    </el-card>

    <!-- 最近记录 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span class="card-title">最近分析</span>
          <el-button link type="primary" @click="goReports">全部记录 →</el-button>
        </div>
      </template>
      <el-table :data="stats?.recent ?? []" empty-text="还没有分析记录，从上方快捷入口开始第一份排查">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="来源" width="120">
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
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              :disabled="row.status !== 'completed'"
              @click="goReports(row.id)"
            >
              {{ row.status === 'completed' ? '查看报告' : '处理中' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChatLineRound, EditPen, Link, UploadFilled } from '@element-plus/icons-vue'
import { contractApi, type ContractStats } from '@/api/contract'
import { sourceLabel, statusLabel, statusTagType, sourceTagType, formatTime } from '@/utils/contractMeta'

const router = useRouter()
const loading = ref(false)
const stats = ref<ContractStats | null>(null)

const fetchStats = async () => {
  loading.value = true
  try {
    const { data } = await contractApi.stats()
    stats.value = data
  } finally {
    loading.value = false
  }
}

const goAnalysis = (tab: string) => router.push({ path: '/analysis', query: { tab } })
const goConsult = () => router.push('/consult')
const goReports = (openId?: string) =>
  router.push({ path: '/reports', query: openId ? { open: openId } : {} })

onMounted(fetchStats)
</script>

<style scoped>
.stat-row {
  margin-bottom: 16px;
}
.hero{background:linear-gradient(125deg,#10233f,#1f5eff);color:#fff;border-radius:14px;padding:28px 32px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center}.hero h1{margin:5px 0;font-size:26px}.hero p{margin:0;color:#cbd9f2}.eyebrow{font-size:11px;letter-spacing:1.5px;color:#9fc0ff}.hero-actions{display:flex;gap:10px}.ops-row{margin-bottom:16px}.pipeline,.review{height:170px}.steps{display:flex;justify-content:space-between;gap:8px}.steps div{display:grid;gap:5px;flex:1}.steps b{color:#1f5eff;font-size:20px}.steps span{font-weight:600}.steps small,.review p{color:#909399}.review-num{font-size:34px;font-weight:700;color:#e96b6b}
.stat-card {
  background: #ffffff;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  padding: 20px;
}
.stat-value {
  font-size: 30px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}
.stat-value.high {
  color: #f56c6c;
}
.stat-label {
  margin-top: 6px;
  font-size: 14px;
  color: #606266;
}
.stat-extra {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  min-height: 20px;
}
.quick-card {
  margin-bottom: 16px;
}
.card-title {
  font-weight: 600;
  color: #303133;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.quick-actions {
  display: flex;
  gap: 16px;
}
.quick-item {
  flex: 1;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.quick-item:hover {
  border-color: #409eff;
  background: #f5f9ff;
  transform: translateY(-2px);
}
.qi-icon {
  font-size: 28px;
}
.qi-icon.text {
  color: #409eff;
}
.qi-icon.file {
  color: #67c23a;
}
.qi-icon.url {
  color: #e6a23c;
}
.qi-icon.consult {
  color: #9c6ade;
}
.qi-name {
  margin-top: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.qi-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}
</style>
