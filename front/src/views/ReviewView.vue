<template>
  <div class="review-page">
    <div class="review-head">
      <div class="file-info">
        <button class="back-btn" title="返回" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <div class="file-thumb">W</div>
        <div class="file-meta">
          <div class="file-name">{{ contractName }}</div>
          <div class="file-sub">
            {{ contractCode }} · {{ pageCount }} 页 · {{ charCount }} 字
            <span v-if="isDemo" class="demo-flag">演示</span>
          </div>
        </div>
      </div>
      <div class="head-actions">
        <el-button @click="downloadReport">
          <el-icon><Download /></el-icon>
          导出报告
        </el-button>
        <el-button type="primary" @click="rerun">
          <el-icon><Refresh /></el-icon>
          重新审查
        </el-button>
      </div>
    </div>

    <div class="review-body">
      <section class="doc-panel">
        <DocViewer
          ref="viewerRef"
          :title="contractName"
          :file-name="fileName"
          :text="contractText"
          :highlights="highlightKeywords"
        />
      </section>

      <aside class="risk-panel qz-panel">
        <div class="risk-head">
          <div>
            <div class="risk-title">AI 初审</div>
            <div class="risk-sub">基于 42 条采购审查规则</div>
          </div>
          <div class="risk-score">
            <el-icon class="score-icon"><WarningFilled /></el-icon>
            <div class="score-meta">
              <span class="score-num">{{ riskScore }}</span>
              <span class="score-label">风险指数</span>
            </div>
          </div>
        </div>

        <div class="risk-tabs">
          <button
            v-for="tab in riskTabs"
            :key="tab.key"
            class="risk-tab"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            <span class="tab-num">{{ tab.count }}</span>
            <span class="tab-label">{{ tab.label }}</span>
          </button>
        </div>

        <ReviewEnhancements
          :facts="contractFacts"
          :clauses="missingClauses"
          :coverage="coverageScore"
        />

        <div class="risk-list" v-loading="loading">
          <article v-for="(risk, index) in visibleRisks" :key="index" class="risk-card">
            <div class="risk-card-head">
              <span class="risk-badge">风险 {{ index + 1 }}</span>
              <span class="qz-chip" :class="`qz-chip--${levelMeta(risk.level).tone}`">
                {{ levelMeta(risk.level).text }}
              </span>
            </div>
            <h3 class="risk-name">{{ risk.title }}</h3>
            <p class="risk-desc">{{ risk.explanation }}</p>
            <div v-if="risk.original_clause" class="clause">
              <span class="clause-label">原文</span>
              {{ risk.original_clause }}
            </div>
            <div v-if="risk.suggested_revision" class="revision">
              <span class="revision-label">建议改为</span>
              {{ risk.suggested_revision }}
            </div>
            <div class="risk-foot">
              <span class="risk-cat">{{ categoryLabel(risk.category) }}</span>
              <button class="locate-btn" @click="locateRisk(risk)">
                <el-icon><Position /></el-icon>
                定位原文
              </button>
            </div>
            <div class="feedback-row">
              <span class="feedback-label">这条结论</span>
              <button
                v-for="opt in feedbackOptions"
                :key="opt.key"
                class="feedback-btn"
                :class="{ active: feedbackMap[feedbackKey(risk)] === opt.key }"
                @click="submitFeedback(risk, opt.key)"
              >
                {{ opt.label }}
              </button>
            </div>
          </article>

          <el-empty v-if="!visibleRisks.length && !loading" description="该等级下暂无风险项" :image-size="64" />
        </div>

        <div class="risk-footer">
          <div v-if="reportSummary" class="summary">{{ reportSummary }}</div>
          <el-button type="primary" class="report-btn" @click="generateReport">
            生成审查报告
          </el-button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Download,
  Position,
  Refresh,
  WarningFilled,
} from '@element-plus/icons-vue'
import DocViewer from '@/components/DocViewer.vue'
import ReviewEnhancements from '@/components/ReviewEnhancements.vue'
import {
  contractApi,
  type ContractFactData,
  type MissingClauseData,
  type RiskItemData,
} from '@/api/contract'
import { reviewApi, type FeedbackVerdict } from '@/api/review'
import { DEMO_CONTRACTS, DEMO_CONTRACT_TEXT } from '@/mock/demo'
import { categoryLabel } from '@/utils/contractMeta'
import { levelMeta } from '@/utils/contractDisplay'
import { isDemoMode } from '@/utils/demoMode'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const isDemo = ref(false)
// 非演示模式不预置任何示例合同的标题/编号/页数，避免与真实数据串味
const contractName = ref(isDemoMode ? '网站开发技术服务合同' : '')
const contractCode = ref(isDemoMode ? 'CT-20260910-018' : '')
const pageCount = ref(0)
const charCount = ref(0)
const contractText = ref(DEMO_CONTRACT_TEXT)
const risks = ref<RiskItemData[]>([])
const reportSummary = ref('')
const riskScore = ref(0)
const activeTab = ref<'all' | 'high' | 'medium' | 'low'>('all')
const viewerRef = ref<InstanceType<typeof DocViewer> | null>(null)

// 审查增强层: 要素核对表 / 缺失条款 / 覆盖率 / 风险反馈
const contractFacts = ref<ContractFactData[]>([])
const missingClauses = ref<MissingClauseData[]>([])
const coverageScore = ref(100)
const feedbackMap = ref<Record<string, FeedbackVerdict>>({})
const feedbackOptions: { key: FeedbackVerdict; label: string }[] = [
  { key: 'accepted', label: '认可' },
  { key: 'false_positive', label: '误报' },
  { key: 'ignored', label: '忽略' },
]
const feedbackKey = (risk: RiskItemData) => risk.id || risk.title

const fileName = computed(() => `${contractName.value.replace(/[\\/:*?"<>|]/g, '')}.docx`)

const DEMO_RISKS: RiskItemData[] = isDemoMode
  ? [
  {
    category: 'non_compete',
    level: 'medium',
    title: '保密义务期限过宽',
    original_clause: '乙方应对甲方提供的商业信息、技术资料承担永久保密义务，未经甲方书面许可，不得向任何第三方披露',
    explanation:
      '永久保密义务缺乏明确的时间边界，可能导致后续执行困难，也可能因约定过度而被认定不合理。建议将保密期限限定为合同终止后 3-5 年，并对已公开信息设置例外。',
    legal_basis: '《中华人民共和国劳动合同法》第二十三条、第二十四条',
    negotiation_tip: '建议改为「保密义务自本合同终止之日起持续五年，且不适用于已进入公有领域的信息」。',
    score: 72,
  },
  {
    category: 'job_description',
    level: 'high',
    title: '逾期未验收视为通过',
    original_clause:
      '甲方应按约定时间组织验收，逾期未验收且未提出书面异议的，视为验收通过',
    explanation:
      '「逾期未验收视为验收通过」虽便于乙方推进结算，但未约定验收的最长期限与分期验收机制，甲方可能长期拖延并在事后主张质量问题，导致尾款结算存在不确定性。建议补充明确的验收期限与书面确认流程。',
    legal_basis: '《中华人民共和国民法典》第五百一十条、第五百一十一条',
    negotiation_tip: '建议约定「甲方应在收到验收申请后 10 个工作日内完成验收并出具书面意见，逾期视为验收通过」。',
    score: 84,
  },
  {
    category: 'jurisdiction',
    level: 'low',
    title: '管辖地约定不利于甲方',
    original_clause: '因本合同引起的争议，双方应友好协商解决；协商不成的，向乙方所在地有管辖权的人民法院提起诉讼',
    explanation:
      '管辖法院约定在乙方所在地，甲方异地维权成本较高。建议改为甲方所在地或合同履行地法院管辖。',
    legal_basis: '《中华人民共和国民事诉讼法》第三十五条',
    negotiation_tip: '建议改为「向甲方所在地有管辖权的人民法院提起诉讼」。',
    score: 40,
  },
  {
    category: 'training_bond',
    level: 'low',
    title: '缺少数据删除证明义务',
    original_clause: '合同终止后，乙方应在 30 日内删除或返还全部甲方数据',
    explanation:
      '条款要求乙方删除数据，但未约定删除完成的书面证明与违约后果，数据合规审计时可能缺少证据链。',
    legal_basis: '《中华人民共和国个人信息保护法》第四十七条',
    negotiation_tip: '建议增加「乙方应在删除完成后 5 个工作日内出具书面删除证明」。',
    score: 36,
  },
] : []

const highlightKeywords = computed(() =>
  risks.value
    .map((risk) => (risk.original_clause || '').trim().slice(0, 8))
    .filter((text) => text.length >= 4)
)

const riskTabs = computed(() => [
  { key: 'all' as const, label: '全部', count: risks.value.length },
  { key: 'high' as const, label: '高风险', count: risks.value.filter((r) => r.level === 'high').length },
  { key: 'medium' as const, label: '中风险', count: risks.value.filter((r) => r.level === 'medium').length },
  { key: 'low' as const, label: '低风险', count: risks.value.filter((r) => r.level === 'low' || r.level === 'safe').length },
])

const visibleRisks = computed(() => {
  if (activeTab.value === 'all') return risks.value
  if (activeTab.value === 'low') {
    return risks.value.filter((risk) => risk.level === 'low' || risk.level === 'safe')
  }
  return risks.value.filter((risk) => risk.level === activeTab.value)
})

const readCachedText = (id: string) => {
  try {
    return sessionStorage.getItem(`qz:contract:${id}`) ?? ''
  } catch {
    return ''
  }
}

const loadContract = async () => {
  const id = typeof route.query.id === 'string' ? route.query.id : ''
  const demo = DEMO_CONTRACTS.find((item) => item.id === id)
  const queryName = typeof route.query.name === 'string' ? route.query.name : ''

  // 切换合同时清掉上一份报告的增强数据, 避免串数据
  contractFacts.value = []
  missingClauses.value = []
  coverageScore.value = 100
  feedbackMap.value = {}

  if (demo) {
    isDemo.value = true
    contractName.value = demo.name
    contractCode.value = demo.code
    pageCount.value = demo.pages
    risks.value = DEMO_RISKS
    return
  }
  if (queryName) contractName.value = queryName
  if (!id) {
    // 非演示模式下没有合同 ID 就是空态，不再回落到示例风险列表
    if (isDemoMode) {
      isDemo.value = true
      risks.value = DEMO_RISKS
    } else {
      isDemo.value = false
      risks.value = []
      contractText.value = ''
    }
    return
  }

  loading.value = true
  try {
    const { data: detail } = await contractApi.get(id)
    const reportRes = await contractApi.getReport(id).catch(() => null)
    const report = reportRes?.data ?? null
    pageCount.value = detail.page_count ?? Math.max(1, Math.ceil((detail.char_count ?? 0) / 1800))
    charCount.value = detail.char_count ?? 0
    contractCode.value = `CT-${String(detail.created_at).slice(0, 10).replace(/-/g, '')}-${id.slice(0, 3).toUpperCase()}`
    const cached = readCachedText(id)
    // 优先会话缓存; 刷新/新标签页无缓存时回落到服务端原文; 最后才用演示文本
    const serverText = typeof detail.raw_text === 'string' ? detail.raw_text.slice(0, 60000) : ''
    contractText.value = cached || serverText || DEMO_CONTRACT_TEXT
    if (report && Array.isArray(report.risk_items)) {
      risks.value = report.risk_items
      reportSummary.value = report.summary
      riskScore.value = Math.max(0, Math.min(100, 100 - (report.overall_score ?? 0)))
      contractFacts.value = report.contract_facts ?? []
      missingClauses.value = report.missing_clauses ?? []
      coverageScore.value = report.coverage_score ?? 100
      // 回显已有的风险反馈, 刷新页面后不丢判定
      const fb = await reviewApi.listFeedback(id).catch(() => null)
      if (fb?.data?.length) {
        const map: Record<string, FeedbackVerdict> = {}
        fb.data.forEach((item) => { map[item.risk_item_id] = item.verdict })
        feedbackMap.value = map
      }
    } else {
      risks.value = []
      ElMessage.info('该合同尚未生成审查报告，可先查看原始文档')
    }
  } catch {
    // 接口失败时不能拿示例结论冒充真实审查结果
    if (isDemoMode) {
      isDemo.value = true
      risks.value = DEMO_RISKS
    } else {
      risks.value = []
      ElMessage.error('报告加载失败，请稍后重试')
    }
  } finally {
    loading.value = false
  }
}

const locateRisk = (risk: RiskItemData) => {
  const needle = (risk.original_clause || '').trim()
  if (!needle) {
    ElMessage.info('该风险项未关联原文条款')
    return
  }
  const hit = viewerRef.value?.locate(needle)
  if (hit) {
    ElMessage.success('已在合同原文中定位该条款')
  } else {
    ElMessage.info('原文中未找到完全匹配的片段，可切换页浏览')
  }
}

const goBack = () => {
  if (window.history.length > 1) router.back()
  else router.push('/reports')
}

const rerun = () => {
  const id = typeof route.query.id === 'string' ? route.query.id : ''
  router.push({ path: '/analysis', query: id ? { id } : {} })
}

const buildReportText = () => {
  const lines = [
    `合同审查报告`,
    `合同名称：${contractName.value}`,
    `合同编号：${contractCode.value}`,
    `风险指数：${riskScore.value}`,
    `必备条款覆盖率：${coverageScore.value}%`,
    reportSummary.value ? `审查结论：${reportSummary.value}` : '',
    '',
  ]
  if (missingClauses.value.length) {
    lines.push('【缺失条款与建议补充】')
    missingClauses.value.forEach((item) => {
      lines.push(`- ${item.label}：${item.suggested_text}`)
    })
    lines.push('')
  }
  risks.value.forEach((risk, index) => {
    lines.push(
      `${index + 1}. [${levelMeta(risk.level).text}] ${risk.title}`,
      `   原文：${risk.original_clause || '—'}`,
      `   解读：${risk.explanation || '—'}`,
      `   依据：${risk.legal_basis || '—'}`,
      `   建议改为：${risk.suggested_revision || '—'}`,
      `   沟通话术：${risk.negotiation_tip || '—'}`,
      ''
    )
  })
  return lines.filter(Boolean).join('\n')
}

const downloadReport = async () => {
  const id = typeof route.query.id === 'string' ? route.query.id : ''
  // 真实合同走后端带批注 Word 导出; 演示数据未落库, 回退到前端文本报告
  if (id && !isDemo.value) {
    try {
      const res = await contractApi.exportReport(id, 'docx')
      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `审查报告-${contractName.value}.docx`
      link.click()
      URL.revokeObjectURL(link.href)
      ElMessage.success('带批注 Word 报告已导出')
      return
    } catch {
      ElMessage.warning('后端导出失败，已回退为文本报告')
    }
  }
  const blob = new Blob([buildReportText()], { type: 'text/plain;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `审查报告-${contractName.value}.txt`
  link.click()
  URL.revokeObjectURL(link.href)
  ElMessage.success('审查报告已导出')
}

const submitFeedback = async (risk: RiskItemData, verdict: FeedbackVerdict) => {
  const contractId = typeof route.query.id === 'string' ? route.query.id : ''
  if (!risk.id || !contractId || isDemo.value) {
    ElMessage.warning('演示数据不支持提交反馈，请先审查一份真实合同')
    return
  }
  try {
    await reviewApi.submitFeedback({
      risk_item_id: risk.id,
      contract_id: contractId,
      verdict,
    })
    feedbackMap.value = { ...feedbackMap.value, [feedbackKey(risk)]: verdict }
    ElMessage.success('反馈已记录，将用于优化审查规则')
  } catch {
    ElMessage.error('反馈提交失败')
  }
}

const generateReport = () => {
  if (!risks.value.length) {
    ElMessage.warning('暂无可生成的风险项，请先完成 AI 审查')
    return
  }
  ElMessage.success('审查报告已生成，可在「审查报告」中查看')
  router.push('/reports')
}

onMounted(loadContract)
</script>

<style scoped>
.revision {
  margin: 8px 0;
  padding: 8px 10px;
  background: #eef4ff;
  border-left: 3px solid var(--qz-primary, #1d4ed8);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--qz-ink-1);
}
.revision-label {
  display: inline-block;
  margin-right: 8px;
  font-weight: 600;
  color: #1d4ed8;
}
.feedback-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px dashed var(--qz-line);
}
.feedback-label {
  font-size: 12px;
  color: var(--qz-ink-3);
  margin-right: auto;
}
.feedback-btn {
  font-size: 12px;
  padding: 3px 9px;
  border: 1px solid var(--qz-line);
  border-radius: 999px;
  background: #ffffff;
  color: var(--qz-ink-2);
  cursor: pointer;
}
.feedback-btn:hover {
  border-color: var(--qz-primary-line, #93b4ff);
  color: var(--qz-primary, #1d4ed8);
}
.feedback-btn.active {
  background: var(--qz-primary, #1d4ed8);
  border-color: var(--qz-primary, #1d4ed8);
  color: #ffffff;
}
.review-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: calc(100vh - 118px);
  min-height: 520px;
}
.review-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: #ffffff;
  border: 1px solid var(--qz-line);
  border-radius: var(--qz-radius);
  box-shadow: var(--qz-shadow);
  padding: 12px 16px;
}
.file-info {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}
.back-btn {
  width: 28px;
  height: 28px;
  border: 1px solid var(--qz-line);
  border-radius: 8px;
  background: #ffffff;
  color: var(--qz-ink-3);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
}
.back-btn:hover {
  color: var(--qz-primary);
  border-color: var(--qz-primary-line);
}
.file-thumb {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: linear-gradient(140deg, #6c4cf1, #9d86fb);
  color: #ffffff;
  font-weight: 700;
  font-size: 13px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.file-meta {
  min-width: 0;
}
.file-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--qz-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-sub {
  margin-top: 3px;
  font-size: 11px;
  color: var(--qz-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.demo-flag {
  padding: 1px 6px;
  border-radius: 5px;
  background: var(--qz-warn-soft);
  color: #b8800f;
  font-size: 10px;
}
.head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.review-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(360px, 1fr);
  gap: 14px;
}
.doc-panel {
  min-width: 0;
  min-height: 0;
}
.risk-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 18px 18px 16px;
}
.risk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}
.risk-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--qz-ink);
}
.risk-sub {
  margin-top: 4px;
  font-size: 11px;
  color: var(--qz-muted);
}
.risk-score {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border-radius: 10px;
  background: var(--qz-danger-soft);
  color: #d93a3f;
}
.score-icon {
  font-size: 14px;
}
.score-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}
.score-num {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.4px;
}
.score-label {
  font-size: 9.5px;
  color: #c25a5e;
}
.risk-tabs {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2px;
  margin: 16px 0 6px;
  padding-bottom: 2px;
  border-bottom: 1px solid var(--qz-line);
  flex-shrink: 0;
}
.risk-tab {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 6px 0 10px;
  border: 0;
  background: transparent;
  cursor: pointer;
  color: var(--qz-ink-3);
}
.risk-tab.active {
  color: var(--qz-primary);
}
.risk-tab.active::after {
  content: "";
  position: absolute;
  left: 18%;
  right: 18%;
  bottom: -1px;
  height: 2px;
  border-radius: 2px;
  background: var(--qz-primary);
}
.tab-num {
  font-size: 15px;
  font-weight: 700;
  color: var(--qz-ink);
}
.risk-tab.active .tab-num {
  color: var(--qz-primary);
}
.tab-label {
  font-size: 10.5px;
  color: var(--qz-muted);
}
.risk-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 4px 4px 0;
  margin-right: -4px;
}
.risk-card {
  border: 1px solid var(--qz-line);
  border-radius: 12px;
  padding: 13px 14px;
  margin-bottom: 10px;
  background: #ffffff;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.risk-card:hover {
  border-color: var(--qz-primary-line);
  box-shadow: 0 8px 20px rgba(28, 26, 60, 0.06);
}
.risk-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.risk-badge {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 6px;
  background: var(--qz-primary-soft);
  color: var(--qz-primary-600);
  font-size: 10.5px;
  font-weight: 600;
}
.risk-name {
  margin: 9px 0 6px;
  font-size: 13.5px;
  font-weight: 650;
  color: var(--qz-ink);
}
.risk-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--qz-ink-2);
}
.clause {
  margin-top: 10px;
  padding: 9px 10px;
  border-left: 2px solid var(--qz-primary-line);
  background: #fbfaff;
  border-radius: 0 8px 8px 0;
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--qz-ink-3);
}
.clause-label {
  display: inline-block;
  margin-right: 5px;
  padding: 0 5px;
  border-radius: 4px;
  background: #efeafd;
  color: var(--qz-primary);
  font-size: 10px;
}
.risk-foot {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.risk-cat {
  font-size: 10.5px;
  color: var(--qz-muted);
}
.locate-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border: 0;
  background: transparent;
  color: var(--qz-primary);
  font-size: 11.5px;
  cursor: pointer;
}
.risk-footer {
  flex-shrink: 0;
  padding-top: 10px;
  border-top: 1px solid var(--qz-line);
}
.summary {
  margin-bottom: 9px;
  padding: 9px 10px;
  border-radius: 8px;
  background: #fafbfe;
  color: var(--qz-ink-3);
  font-size: 11.5px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.report-btn {
  width: 100%;
  height: 38px;
}

@media (max-width: 1180px) {
  .review-page {
    height: auto;
  }
  .review-body {
    grid-template-columns: minmax(0, 1fr);
  }
  .doc-panel {
    height: 620px;
  }
  .risk-panel {
    max-height: 620px;
  }
}
</style>
