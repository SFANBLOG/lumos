<template>
  <div class="analysis">
    <el-card shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- ── 粘贴文本 ─────────────────────────────── -->
        <el-tab-pane name="text">
          <template #label>
            <span class="tab-label"><el-icon><EditPen /></el-icon>粘贴文本</span>
          </template>
          <div class="tab-body">
            <el-input
              v-model="pasteText"
              type="textarea"
              :rows="12"
              placeholder="请将劳动合同全文粘贴到这里，至少 10 个字…"
              :disabled="analyzing"
              show-word-limit
              maxlength="100000"
            />
            <div class="row-actions">
              <el-button
                type="primary"
                :loading="analyzing"
                :disabled="!pasteText.trim() || analyzing"
                @click="start('text')"
              >
                开始分析
              </el-button>
              <el-button :disabled="analyzing" @click="clearTextTab">清空</el-button>
              <span class="hint">文本仅用于本次分析，不会公开</span>
            </div>
          </div>
        </el-tab-pane>

        <!-- ── 上传文件 ─────────────────────────────── -->
        <el-tab-pane name="file">
          <template #label>
            <span class="tab-label"><el-icon><UploadFilled /></el-icon>上传文件</span>
          </template>
          <div class="tab-body">
            <el-upload
              drag
              action="#"
              accept=".pdf,.txt,.docx,.csv"
              :auto-upload="true"
              :show-file-list="false"
              :http-request="onFileUpload"
              :before-upload="beforeFileUpload"
              :disabled="analyzing"
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">将文件拖到此处，或 <em>点击选择文件</em></div>
              <template #tip>
                <div class="el-upload__tip">支持 PDF / TXT / DOCX / CSV，单个文件不超过 10MB</div>
              </template>
            </el-upload>

            <div v-if="fileParsing" class="ingest-tip">正在解析文件，请稍候…</div>

            <template v-if="fileMeta">
              <div class="meta-bar">
                <el-tag type="success" size="small">{{ fileMeta.ext.toUpperCase() }}</el-tag>
                <span class="meta-text">{{ fileMeta.filename }}</span>
                <span class="meta-sub">
                  已抽取 {{ fileMeta.char_count }} 字
                  <template v-if="fileMeta.scanned"> · ⚠️ 疑似扫描件，可能无文字层</template>
                </span>
                <el-button link type="danger" size="small" @click="clearFileTab">移除</el-button>
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
                :rows="10"
                placeholder="抽取出的文本，可编辑后分析…"
                :disabled="analyzing"
              />
              <div class="row-actions">
                <el-button
                  type="primary"
                  :loading="analyzing"
                  :disabled="fileText.trim().length < 10 || analyzing"
                  @click="start('file')"
                >
                  分析抽取文本
                </el-button>
              </div>
            </template>
          </div>
        </el-tab-pane>

        <!-- ── 网页链接 ─────────────────────────────── -->
        <el-tab-pane name="url">
          <template #label>
            <span class="tab-label"><el-icon><Link /></el-icon>网页链接</span>
          </template>
          <div class="tab-body">
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
                <el-tag type="primary" size="small">URL</el-tag>
                <span class="meta-text">{{ urlMeta.title || urlMeta.url }}</span>
                <span class="meta-sub">已抽取 {{ urlMeta.char_count }} 字</span>
                <el-button link type="danger" size="small" @click="clearUrlTab">移除</el-button>
              </div>
              <el-alert
                v-if="urlMeta.truncated"
                title="页面较长，仅截取前 100,000 字用于分析"
                type="warning"
                :closable="false"
                class="truncate-alert"
              />
              <el-input
                v-model="urlText"
                type="textarea"
                :rows="10"
                placeholder="解析出的正文，可编辑后分析…"
                :disabled="analyzing"
              />
              <div class="row-actions">
                <el-button
                  type="primary"
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
    </el-card>

    <!-- ── 共享分析进度区 ─────────────────────────── -->
    <el-card v-if="analyzing || risks.length || statusMessage" shadow="never" class="result-card">
      <template #header>
        <div class="result-head">
          <span class="card-title">分析结果</span>
          <el-button
            v-if="contractId && !analyzing && statusMessage === '分析完成'"
            link
            type="primary"
            @click="goReport"
          >
            查看完整报告 →
          </el-button>
        </div>
      </template>
      <div v-if="statusMessage" class="status">{{ statusMessage }}</div>
      <el-progress
        v-if="analyzing"
        :percentage="Math.max(5, Math.round(progress * 100))"
        :status="analyzing ? undefined : 'success'"
      />
      <div v-if="risks.length" class="risks">
        <div class="risks-title">已发现 {{ risks.length }} 项风险</div>
        <el-collapse>
          <el-collapse-item v-for="(risk, idx) in risks" :key="idx" :title="risk.title">
            <div class="risk-tags">
              <el-tag size="small" :type="levelTagType(risk.level)">{{ levelLabel(risk.level) }}</el-tag>
              <el-tag size="small" type="info" effect="plain">{{ categoryLabel(risk.category) }}</el-tag>
            </div>
            <p><strong>原始条文：</strong>{{ risk.original_clause }}</p>
            <p><strong>大白话解读：</strong>{{ risk.explanation }}</p>
            <p v-if="risk.legal_basis"><strong>法律依据：</strong>{{ risk.legal_basis }}</p>
            <p v-if="risk.negotiation_tip"><strong>谈判话术：</strong>{{ risk.negotiation_tip }}</p>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type UploadRawFile, type UploadRequestOptions } from 'element-plus'
import { EditPen, Link, UploadFilled } from '@element-plus/icons-vue'
import { contractApi } from '@/api/contract'
import { ingestApi, type FileIngestResponse, type UrlIngestResponse } from '@/api/ingest'
import { categoryLabel, levelLabel, levelTagType } from '@/utils/contractMeta'

const route = useRoute()
const router = useRouter()

type TabName = 'text' | 'file' | 'url'
const TAB_NAMES: TabName[] = ['text', 'file', 'url']

const activeTab = ref<TabName>('text')

// 三个来源的输入
const pasteText = ref('')
const fileText = ref('')
const fileMeta = ref<FileIngestResponse | null>(null)
const fileParsing = ref(false)
const urlInput = ref('')
const urlText = ref('')
const urlMeta = ref<UrlIngestResponse | null>(null)
const urlParsing = ref(false)

// 共享分析状态
const analyzing = ref(false)
const progress = ref(0)
const statusMessage = ref('')
const risks = ref<any[]>([])
const contractId = ref('')
let eventSource: EventSource | null = null

// ── 路由 query.tab 双向同步 ────────────────────────
const syncTabFromRoute = () => {
  const q = route.query.tab
  if (typeof q === 'string' && (TAB_NAMES as string[]).includes(q)) {
    activeTab.value = q as TabName
  }
}
const onTabChange = (name: string | number) => {
  if (route.query.tab !== name) {
    router.replace({ query: { ...route.query, tab: String(name) } })
  }
}

// ── 文件上传 (el-upload http-request 自定义走 axios) ─
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

// ── 链接解析 ───────────────────────────────────────
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

// ── 统一分析流程 ───────────────────────────────────
const sourceFor = (tab: TabName) => (tab === 'file' ? 'file_upload' : tab === 'url' ? 'url_analysis' : 'text_paste')

const start = async (tab: TabName) => {
  const text = tab === 'text' ? pasteText.value : tab === 'file' ? fileText.value : urlText.value
  if (text.trim().length < 10) {
    ElMessage.warning('文本至少需要 10 个字')
    return
  }
  analyzing.value = true
  progress.value = 0
  statusMessage.value = '正在提交合同…'
  risks.value = []
  contractId.value = ''

  try {
    const { data } = await contractApi.submit({ text, source: sourceFor(tab) })
    contractId.value = data.contract_id
    statusMessage.value = data.message
    eventSource = contractApi.stream(data.contract_id, (event) => handleEvent(event))
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
    analyzing.value = false
  }
}

const handleEvent = (event: { event: string; data: any }) => {
  switch (event.event) {
    case 'thinking':
      statusMessage.value = event.data.message || 'Agent 思考中…'
      break
    case 'node_start':
      statusMessage.value = event.data.description
      progress.value = event.data.progress ?? progress.value
      break
    case 'node_complete':
      statusMessage.value = event.data.description
      progress.value = event.data.progress ?? progress.value
      break
    case 'risk_found':
      risks.value.push(event.data)
      break
    case 'summary':
      statusMessage.value = event.data.summary || '分析完成'
      break
    case 'complete':
      statusMessage.value = '分析完成'
      analyzing.value = false
      eventSource?.close()
      ElMessage.success('分析完成，可在下方查看逐条风险')
      break
    case 'error':
      statusMessage.value = event.data.message || '分析失败'
      analyzing.value = false
      eventSource?.close()
      ElMessage.error(event.data.message || '分析失败')
      break
  }
}

const goReport = () => {
  if (contractId.value) {
    router.push({ path: '/reports', query: { open: contractId.value } })
  }
}

// ── 清理 ───────────────────────────────────────────
const clearTextTab = () => {
  pasteText.value = ''
}
const clearFileTab = () => {
  fileMeta.value = null
  fileText.value = ''
}
const clearUrlTab = () => {
  urlMeta.value = null
  urlText.value = ''
  urlInput.value = ''
}

onMounted(syncTabFromRoute)
onBeforeUnmount(() => eventSource?.close())
</script>

<style scoped>
.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.tab-body {
  padding: 4px 0 8px;
}
.row-actions {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.hint {
  font-size: 12px;
  color: #909399;
}
.ingest-tip {
  margin-top: 12px;
  color: #909399;
  font-size: 13px;
}
.url-row {
  display: flex;
  gap: 10px;
  margin-bottom: 4px;
}
.meta-bar {
  margin: 14px 0 10px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.meta-text {
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta-sub {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}
.truncate-alert {
  margin-bottom: 10px;
}
.result-card {
  margin-top: 16px;
}
.result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title {
  font-weight: 600;
  color: #303133;
}
.status {
  margin: 6px 0 14px;
  color: #606266;
}
.risks {
  margin-top: 18px;
}
.risks-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}
.risk-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.risks p {
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
}
.risks p strong {
  color: #303133;
}
</style>
