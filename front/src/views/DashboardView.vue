<template>
  <div class="dashboard" v-loading="loading">
    <section class="hero">
      <div><span class="eyebrow">LUMOS AGENT OPERATIONS</span><h1>合同审查控制台</h1><p>将企业 Playbook、证据质检与人工审批置于同一条可审计工作流。</p></div>
      <div class="hero-actions"><el-button type="primary" size="large" @click="goAnalysis('file')">提交审查任务</el-button><el-button size="large" @click="goReports()">进入合同库</el-button></div>
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
      <el-col :span="9"><el-card shadow="never" class="review"><template #header><span class="card-title">待处理事项</span></template><div class="review-num">{{ stats?.high_risk_contracts ?? 0 }}</div><p>高风险合同等待人工复核</p><el-button link type="primary" @click="goReports()">查看审查队列 →</el-button></el-card></el-col>
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
          <el-button link type="primary" @click="goReports()">全部记录 →</el-button>
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
.hero{background:linear-gradient(120deg,#0b1f33,#193b59);color:#fff;border-radius:12px;padding:30px 34px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 14px 30px rgba(16,42,67,.12)}.hero h1{margin:6px 0;font-size:28px;letter-spacing:.2px}.hero p{margin:0;color:#c6d5e5;font-size:15px}.eyebrow{font-size:11px;letter-spacing:1.8px;color:#8eb7e8}.hero-actions{display:flex;gap:10px}.hero-actions .el-button:not(.el-button--primary){border-color:rgba(255,255,255,.4);color:#fff;background:transparent}.ops-row{margin-bottom:20px}.pipeline,.review{min-height:180px}.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:0}.steps div{display:grid;gap:7px;padding:6px 18px;border-left:1px solid var(--line)}.steps div:first-child{border-left:0;padding-left:0}.steps b{color:var(--brand);font-size:20px}.steps span{font-weight:650;color:var(--ink-900)}.steps small,.review p{color:var(--ink-600)}.review-num{font-size:34px;font-weight:700;color:var(--accent)}
.stat-card {
  background: var(--paper);
  border-radius: 12px;
  border: 1px solid var(--line);
  padding: 22px;
}
.stat-value {
  font-size: 30px;
  font-weight: 700;
  color: var(--ink-900);
  line-height: 1.2;
}
.stat-value.high {
  color: var(--accent);
}
.stat-label {
  margin-top: 6px;
  font-size: 14px;
  color: var(--ink-600);
}
.stat-extra {
  margin-top: 6px;
  font-size: 12px;
  color: #7b8ca0;
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
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.quick-item:hover {
  border-color: var(--brand);
  background: var(--brand-soft);
  transform: translateY(-2px);
}
.qi-icon {
  font-size: 28px;
}
.qi-icon.text,.qi-icon.file,.qi-icon.url,.qi-icon.consult { color: var(--brand); }
.qi-name {
  margin-top: 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-900);
}
.qi-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ink-600);
}
@media (max-width: 1100px){.hero{align-items:flex-start;gap:20px}.steps{grid-template-columns:repeat(2,1fr)}.steps div:nth-child(3){border-left:0}.quick-actions{flex-wrap:wrap}.quick-item{min-width:40%}}
</style>
