<template>
  <div class="qz-page">
    <div class="flow-bar">
      <div class="flow-actions">
        <el-button type="primary" @click="resetTask">
          <el-icon><Plus /></el-icon>
          新建任务
        </el-button>
        <el-button @click="router.push('/reports')">
          <el-icon><Tickets /></el-icon>
          审查历史
        </el-button>
      </div>
      <div class="flow-hint">
        <el-icon><Lock /></el-icon>
        合同文件仅在本地加密存储，传输与解析全程留痕
      </div>
    </div>

    <section class="qz-panel flow-panel">
      <el-steps :active="stepIndex" align-center class="flow-steps" finish-status="success">
        <el-step title="上传合同文件" />
        <el-step title="AI 审查" />
        <el-step title="AI 初审" />
        <el-step title="人工复核" />
        <el-step title="生成报告" />
      </el-steps>

      <div v-if="stage === 'upload'" class="upload-stage">
        <el-tabs v-model="activeTab" class="upload-tabs" @tab-change="onTabChange">
          <el-tab-pane name="file">
            <template #label>
              <span class="tab-label"><el-icon><UploadFilled /></el-icon>上传文件</span>
            </template>
            <div class="pane-body">
              <el-upload
                v-if="!fileMeta && !fileParsing"
                drag
                action="#"
                accept=".pdf,.txt,.docx,.csv,.md,.html,.htm,.rtf,.xlsx,.pptx,.png,.jpg,.jpeg,.gif,.webp,.bmp"
                :auto-upload="true"
                :show-file-list="false"
                :http-request="onFileUpload"
                :before-upload="beforeFileUpload"
                class="drop-zone"
              >
                <div class="drop-icon"><el-icon><UploadFilled /></el-icon></div>
                <div class="drop-title">将合同文件拖到此处，或 <em>点击选择文件</em></div>
                <div class="drop-sub">
                  支持 PDF / Word / TXT / Excel / 图片（自动 OCR），单个文件不超过 10MB
                </div>
              </el-upload>

              <div v-if="fileParsing" class="parsing-card">
                <el-icon class="spin"><Loading /></el-icon>
                <div>
                  <div class="parsing-title">正在解析文件内容</div>
                  <div class="parsing-sub">文档结构识别与文字抽取中，请稍候…</div>
                </div>
              </div>

              <div v-if="fileMeta" class="parsed-card">
                <AppImage
                  v-if="imagePreview"
                  :src="imagePreview"
                  width="104px"
                  height="132px"
                  radius="10px"
                  fit="cover"
                  previewable
                  :lazy="false"
                  alt="上传的合同图片"
                  caption="点击放大"
                />
                <div v-else class="file-cover"><el-icon><Document /></el-icon></div>
                <div class="parsed-meta">
                  <div class="parsed-name">{{ fileMeta.filename }}</div>
                  <div class="parsed-sub">
                    <span class="qz-chip qz-chip--primary">{{ fileMeta.ext.toUpperCase() }}</span>
                    <span>已抽取 {{ fileMeta.char_count.toLocaleString() }} 字</span>
                    <span v-if="fileMeta.scanned" class="qz-chip qz-chip--warn">疑似扫描件</span>
                  </div>
                  <el-alert
                    v-if="fileMeta.truncated"
                    title="文件较长，仅截取前 100,000 字用于分析"
                    type="warning"
                    :closable="false"
                    class="truncate-alert"
                  />
                  <el-input
                    v-model="fileText"
                    type="textarea"
                    :rows="5"
                    placeholder="抽取出的文本，可编辑后分析…"
                    :disabled="analyzing"
                    class="text-preview"
                  />
                </div>
                <el-button link type="danger" class="remove-file" @click="clearFileTab">移除</el-button>
              </div>

              <div class="pane-actions">
                <el-button
                  type="primary"
                  size="large"
                  :loading="analyzing"
                  :disabled="fileText.trim().length < 10"
                  @click="start('file')"
                >
                  开始 AI 审查
                </el-button>
                <span class="pane-tip">提交后将进入 AI 审查 → 初审 → 人工复核流程</span>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane name="text">
            <template #label>
              <span class="tab-label"><el-icon><EditPen /></el-icon>粘贴文本</span>
            </template>
            <div class="pane-body">
              <el-input
                v-model="pasteText"
                type="textarea"
                :rows="14"
                placeholder="请将劳动合同全文粘贴到这里，至少 10 个字…"
                :disabled="analyzing"
                show-word-limit
                maxlength="100000"
              />
              <div class="pane-actions">
                <el-button
                  type="primary"
                  size="large"
                  :loading="analyzing"
                  :disabled="!pasteText.trim() || analyzing"
                  @click="start('text')"
                >
                  开始 AI 审查
                </el-button>
                <el-button size="large" :disabled="analyzing" @click="pasteText = ''">清空</el-button>
                <span class="pane-tip">文本仅用于本次分析，不会公开</span>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane name="url">
            <template #label>
              <span class="tab-label"><el-icon><Link /></el-icon>网页链接</span>
            </template>
            <div class="pane-body">
              <div class="url-row">
                <el-input
                  v-model="urlInput"
                  placeholder="粘贴合同/条款的网页链接，如 https://example.com/contract.html"
                  :disabled="analyzing || urlParsing"
                  clearable
                  @keyup.enter="parseUrl"
                />
                <el-button
                  type="primary"
                  :loading="urlParsing"
                  :disabled="!urlInput.trim() || analyzing"
                  @click="parseUrl"
                >
                  解析页面
                </el-button>
              </div>

              <template v-if="urlMeta">
                <div class="meta-bar">
                  <span class="qz-chip qz-chip--info">URL</span>
                  <span class="meta-text">{{ urlMeta.title || urlMeta.url }}</span>
                  <span class="meta-sub">已抽取 {{ urlMeta.char_count }} 字</span>
                  <el-button link type="danger" @click="clearUrlTab">移除</el-button>
                </div>
                <el-input v-model="urlText" type="textarea" :rows="9" placeholder="解析出的正文，可编辑后分析…" />
                <div class="pane-actions">
                  <el-button
                    type="primary"
                    size="large"
                    :loading="analyzing"
                    :disabled="urlText.trim().length < 10 || analyzing"
                    @click="start('url')"
                  >
                    分析网页内容
                  </el-button>
                </div>
              </template>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>

      <div v-else-if="stage === 'analyzing'" class="analyzing-stage">
        <div class="spinner-ring">
          <el-icon class="spin"><Loading /></el-icon>
        </div>
        <h2>AI 正在审查合同</h2>
        <p>{{ statusMessage || '系统正在处理文档内容并执行 AI 审查，请稍候' }}</p>
        <div class="progress-wrap">
          <el-progress
            :percentage="percent"
            :show-text="false"
            :stroke-width="10"
            color="#6c4cf1"
            class="flow-progress"
          />
          <div class="progress-meta">
            <span>{{ currentStageText }}</span>
            <span class="percent">{{ percent }}%</span>
          </div>
        </div>
        <el-button type="danger" size="large" class="stop-btn" @click="stopAnalysis">
          停止审查
        </el-button>
        <div class="analyzing-note">
          预计耗时 2-3 分钟 · 已完成条款抽取与规则匹配，正在生成初审意见
        </div>
      </div>

      <div v-else-if="stage === 'done'" class="done-stage">
        <div class="done-icon"><el-icon><CircleCheckFilled /></el-icon></div>
        <h2>AI 初审已完成</h2>
        <p>共发现 {{ risks.length }} 项风险，可进入初审页逐条核对原文并生成报告。</p>
        <div class="done-actions">
          <el-button type="primary" size="large" @click="goReview">查看 AI 初审</el-button>
          <el-button size="large" @click="resetTask">再传一份</el-button>
        </div>
      </div>

      <div v-else class="done-stage">
        <div class="done-icon error"><el-icon><WarningFilled /></el-icon></div>
        <h2>审查未完成</h2>
        <p>{{ statusMessage || '分析过程出现异常，请稍后重试' }}</p>
        <div class="done-actions">
          <el-button type="primary" @click="resetTask">重新提交</el-button>
        </div>
      </div>
    </section>

    <section v-if="risks.length" class="qz-panel">
      <div class="qz-panel-head">
        <div>
          <div class="qz-panel-title">实时风险清单</div>
          <div class="qz-panel-sub">AI 边审边出结论，可先处理高风险条款</div>
        </div>
        <span class="qz-chip qz-chip--primary">已发现 {{ risks.length }} 项</span>
      </div>
      <div class="qz-panel-body risk-grid">
        <div v-for="(risk, index) in risks" :key="index" class="risk-row">
          <div class="risk-row-head">
            <span class="qz-chip" :class="`qz-chip--${levelMeta(risk.level).tone}`">
              {{ levelMeta(risk.level).text }}
            </span>
            <span class="risk-title">{{ risk.title }}</span>
          </div>
          <p>{{ risk.explanation }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type UploadRawFile, type UploadRequestOptions } from 'element-plus'
import {
  CircleCheckFilled,
  Document,
  EditPen,
  Link,
  Loading,
  Lock,
  Plus,
  Tickets,
  UploadFilled,
  WarningFilled,
} from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import { contractApi } from '@/api/contract'
import { ingestApi, type FileIngestResponse, type UrlIngestResponse } from '@/api/ingest'
import { levelMeta } from '@/utils/contractDisplay'

const route = useRoute()
const router = useRouter()

type TabName = 'text' | 'file' | 'url'
const TAB_NAMES: TabName[] = ['text', 'file', 'url']
const activeTab = ref<TabName>('file')

const pasteText = ref('')
const fileText = ref('')
const fileMeta = ref<FileIngestResponse | null>(null)
const fileParsing = ref(false)
const imagePreview = ref('')
const urlInput = ref('')
const urlText = ref('')
const urlMeta = ref<UrlIngestResponse | null>(null)
const urlParsing = ref(false)

const stage = ref<'upload' | 'analyzing' | 'done' | 'failed'>('upload')
const analyzing = computed(() => stage.value === 'analyzing')
const progress = ref(0)
const statusMessage = ref('')
const risks = ref<any[]>([])
const contractId = ref('')
let eventSource: EventSource | null = null
let progressTimer: number | null = null

const stepIndex = computed(() => {
  if (stage.value === 'upload') return 0
  if (stage.value === 'analyzing') return progress.value > 0.6 ? 2 : 1
  if (stage.value === 'done') return 4
  return 1
})

const percent = computed(() => Math.max(5, Math.round(progress.value * 100)))

const currentStageText = computed(() => {
  if (progress.value < 0.35) return '解析文档结构与条款'
  if (progress.value < 0.7) return '匹配审查规则与法条依据'
  return '生成风险清单与初审意见'
})

const syncTabFromRoute = () => {
  const query = route.query.tab
  if (typeof query === 'string' && (TAB_NAMES as string[]).includes(query)) {
    activeTab.value = query as TabName
  }
}

const onTabChange = (name: string | number) => {
  if (route.query.tab !== name) {
    router.replace({ query: { ...route.query, tab: String(name) } })
  }
}

const beforeFileUpload = (file: UploadRawFile) => {
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('文件超过 10MB 上限')
    return false
  }
  return true
}

const onFileUpload = async (options: UploadRequestOptions) => {
  fileParsing.value = true
  try {
    const data = await ingestApi.uploadFile(options.file)
    fileMeta.value = data
    fileText.value = data.text
    if (options.file.type.startsWith('image/')) {
      if (imagePreview.value) URL.revokeObjectURL(imagePreview.value)
      imagePreview.value = URL.createObjectURL(options.file)
    }
    if (data.truncated) {
      ElMessage.warning('文件较长，仅截取前 100,000 字')
    }
    if (data.scanned && !data.text.trim()) {
      ElMessage.warning('该 PDF 没有可抽取的文字层，请改用文本粘贴或上传带文字层的文件')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '文件解析失败')
  } finally {
    fileParsing.value = false
  }
}

const parseUrl = async () => {
  const url = urlInput.value.trim()
  if (!url) return
  urlParsing.value = true
  try {
    const data = await ingestApi.ingestUrl(url)
    urlMeta.value = data
    urlText.value = data.text
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '页面解析失败')
  } finally {
    urlParsing.value = false
  }
}

const sourceFor = (tab: TabName) =>
  tab === 'file' ? 'file_upload' : tab === 'url' ? 'url_analysis' : 'text_paste'

const startProgressTimer = () => {
  stopProgressTimer()
  progressTimer = window.setInterval(() => {
    if (progress.value < 0.95) {
      progress.value = Math.min(0.95, progress.value + 0.008)
    }
  }, 700)
}

const stopProgressTimer = () => {
  if (progressTimer) {
    window.clearInterval(progressTimer)
    progressTimer = null
  }
}

const start = async (tab: TabName) => {
  const text = tab === 'text' ? pasteText.value : tab === 'file' ? fileText.value : urlText.value
  if (text.trim().length < 10) {
    ElMessage.warning('文本至少需要 10 个字')
    return
  }
  stage.value = 'analyzing'
  progress.value = 0.06
  statusMessage.value = '正在提交合同…'
  risks.value = []
  contractId.value = ''
  startProgressTimer()

  try {
    const { data } = await contractApi.submit({ text, source: sourceFor(tab) })
    contractId.value = data.contract_id
    statusMessage.value = data.message
    try {
      sessionStorage.setItem(`qz:contract:${data.contract_id}`, text.slice(0, 60000))
    } catch {
      /* 超大文本缓存失败时不影响分析 */
    }
    eventSource = contractApi.stream(data.contract_id, (event) => handleEvent(event))
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
    stage.value = 'failed'
    statusMessage.value = e.response?.data?.detail || '提交失败'
    stopProgressTimer()
  }
}

const handleEvent = (event: { event: string; data: any }) => {
  switch (event.event) {
    case 'thinking':
      statusMessage.value = event.data.message || 'Agent 思考中…'
      break
    case 'node_start':
      statusMessage.value = event.data.description
      progress.value = Math.max(progress.value, event.data.progress ?? progress.value)
      break
    case 'node_complete':
      statusMessage.value = event.data.description
      progress.value = Math.max(progress.value, event.data.progress ?? progress.value)
      break
    case 'risk_found':
      risks.value.push(event.data)
      break
    case 'summary':
      statusMessage.value = event.data.summary || '分析完成'
      break
    case 'complete':
      progress.value = 1
      statusMessage.value = '分析完成'
      stage.value = 'done'
      stopProgressTimer()
      eventSource?.close()
      ElMessage.success('AI 初审完成')
      break
    case 'error':
      statusMessage.value = event.data.message || '分析失败'
      stage.value = 'failed'
      stopProgressTimer()
      eventSource?.close()
      ElMessage.error(event.data.message || '分析失败')
      break
  }
}

const stopAnalysis = () => {
  eventSource?.close()
  eventSource = null
  stopProgressTimer()
  stage.value = 'upload'
  progress.value = 0
  ElMessage.info('已停止本次审查')
}

const goReview = () => {
  if (!contractId.value) {
    router.push('/reports')
    return
  }
  const fileName = fileMeta.value?.filename ?? '合同'
  router.push({
    path: '/review',
    query: { id: contractId.value, name: fileName.replace(/\.[^.]+$/, '') },
  })
}

const resetTask = () => {
  stopAnalysis()
  fileMeta.value = null
  fileText.value = ''
  urlMeta.value = null
  urlText.value = ''
  urlInput.value = ''
  pasteText.value = ''
  risks.value = []
  if (imagePreview.value) {
    URL.revokeObjectURL(imagePreview.value)
    imagePreview.value = ''
  }
  stage.value = 'upload'
}

const clearFileTab = () => {
  fileMeta.value = null
  fileText.value = ''
  if (imagePreview.value) {
    URL.revokeObjectURL(imagePreview.value)
    imagePreview.value = ''
  }
}

const clearUrlTab = () => {
  urlMeta.value = null
  urlText.value = ''
  urlInput.value = ''
}

onMounted(syncTabFromRoute)

onBeforeUnmount(() => {
  eventSource?.close()
  stopProgressTimer()
  if (imagePreview.value) URL.revokeObjectURL(imagePreview.value)
})
</script>

<style scoped>
.flow-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.flow-actions {
  display: flex;
  gap: 10px;
}
.flow-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--qz-muted);
}
.flow-panel {
  padding: 22px 24px 26px;
  min-height: 520px;
  display: flex;
  flex-direction: column;
}
.flow-steps {
  padding: 4px 10px 12px;
  border-bottom: 1px solid var(--qz-line);
  margin-bottom: 22px;
}
.flow-steps :deep(.el-step__title) {
  font-size: 12.5px;
  line-height: 1.4;
}
.upload-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.upload-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}
.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.pane-body {
  padding: 4px 2px 8px;
}
.drop-zone {
  display: block;
}
.drop-zone :deep(.el-upload) {
  width: 100%;
}
.drop-zone :deep(.el-upload-dragger) {
  width: 100%;
  padding: 46px 20px;
  border: 1.5px dashed var(--qz-primary-line);
  border-radius: 14px;
  background: linear-gradient(180deg, #fbfaff, #ffffff);
  transition: border-color 0.2s ease, background 0.2s ease;
}
.drop-zone :deep(.el-upload-dragger:hover) {
  border-color: var(--qz-primary);
  background: #faf8ff;
}
.drop-icon {
  width: 54px;
  height: 54px;
  margin: 0 auto 14px;
  border-radius: 14px;
  background: var(--qz-primary-soft);
  color: var(--qz-primary);
  display: grid;
  place-items: center;
  font-size: 25px;
}
.drop-title {
  font-size: 14px;
  color: var(--qz-ink-2);
}
.drop-title em {
  color: var(--qz-primary);
  font-style: normal;
  font-weight: 600;
}
.drop-sub {
  margin-top: 8px;
  font-size: 11.5px;
  color: var(--qz-muted);
}
.parsing-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 26px;
  border: 1px solid var(--qz-line);
  border-radius: 14px;
  color: var(--qz-primary);
  font-size: 22px;
}
.parsing-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--qz-ink);
}
.parsing-sub {
  margin-top: 5px;
  font-size: 12px;
  color: var(--qz-muted);
}
.parsed-card {
  position: relative;
  display: flex;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--qz-line);
  border-radius: 14px;
  background: #fcfcfe;
}
.file-cover {
  width: 104px;
  height: 132px;
  border-radius: 10px;
  background: linear-gradient(150deg, #f2eefe, #e7e1fd);
  color: var(--qz-primary);
  display: grid;
  place-items: center;
  font-size: 34px;
  flex-shrink: 0;
}
.parsed-meta {
  flex: 1;
  min-width: 0;
}
.parsed-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--qz-ink);
  margin-bottom: 8px;
  word-break: break-all;
}
.parsed-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--qz-muted);
  flex-wrap: wrap;
}
.truncate-alert {
  margin-top: 10px;
}
.text-preview {
  margin-top: 12px;
}
.remove-file {
  position: absolute;
  top: 12px;
  right: 12px;
}
.pane-actions {
  margin-top: 18px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.pane-tip {
  font-size: 11.5px;
  color: var(--qz-muted);
}
.url-row {
  display: flex;
  gap: 10px;
}
.meta-bar {
  margin: 14px 0 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.meta-text {
  font-weight: 600;
  color: var(--qz-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta-sub {
  font-size: 12px;
  color: var(--qz-muted);
  flex-shrink: 0;
}

.analyzing-stage,
.done-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 26px 20px 40px;
}
.spinner-ring {
  width: 66px;
  height: 66px;
  border-radius: 50%;
  background: var(--qz-primary-soft);
  color: var(--qz-primary);
  display: grid;
  place-items: center;
  font-size: 28px;
  margin-bottom: 18px;
}
.spin {
  animation: qz-spin 1.1s linear infinite;
}
@keyframes qz-spin {
  to {
    transform: rotate(360deg);
  }
}
.analyzing-stage h2,
.done-stage h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--qz-ink);
}
.analyzing-stage p,
.done-stage p {
  margin: 9px 0 0;
  font-size: 13px;
  color: var(--qz-ink-3);
  max-width: 560px;
  line-height: 1.7;
}
.progress-wrap {
  width: min(520px, 86%);
  margin: 26px 0 20px;
}
.flow-progress :deep(.el-progress-bar__outer) {
  background: #f0edfd;
}
.progress-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 12px;
  color: var(--qz-muted);
}
.percent {
  color: var(--qz-primary);
  font-weight: 650;
}
.stop-btn {
  min-width: 132px;
}
.analyzing-note {
  margin-top: 16px;
  font-size: 11.5px;
  color: #b0b4c4;
}
.done-icon {
  width: 62px;
  height: 62px;
  border-radius: 50%;
  background: var(--qz-success-soft);
  color: var(--qz-success);
  display: grid;
  place-items: center;
  font-size: 30px;
  margin-bottom: 16px;
}
.done-icon.error {
  background: var(--qz-danger-soft);
  color: var(--qz-danger);
}
.done-actions {
  margin-top: 22px;
  display: flex;
  gap: 10px;
}
.risk-grid {
  display: grid;
  gap: 10px;
}
.risk-row {
  padding: 12px 14px;
  border: 1px solid var(--qz-line);
  border-radius: 11px;
}
.risk-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.risk-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink);
}
.risk-row p {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--qz-ink-2);
}
</style>
