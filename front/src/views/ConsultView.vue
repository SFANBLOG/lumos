<template>
  <div class="consult">
    <el-card shadow="never" class="chat-card">
      <!-- ── 顶栏: 关联报告 ─────────────────── -->
      <!-- 历史会话已迁至左侧「智能咨询」子菜单; 顶栏仅保留「关联报告」与「新对话」 -->
      <template #header>
        <div class="toolbar">
          <el-button :disabled="answering" @click="startNewChat">新对话</el-button>
          <span class="toolbar-sep" />
          <span class="toolbar-label">关联报告</span>
          <el-select
            v-model="contractSel"
            class="contract-sel"
            placeholder="不关联 (通用问答)"
            clearable
            filterable
            :disabled="answering"
          >
            <el-option
              v-for="c in contracts"
              :key="c.id"
              :value="c.id"
              :label="`${previewLabel(c.preview)} · ${formatTime(c.created_at)}`"
            />
          </el-select>
          <span v-if="contractSel" class="hint">问答将结合该报告的已分析风险项</span>
          <span v-else-if="currentSessionTitle" class="current-session">
            当前会话：{{ currentSessionTitle }}
          </span>
        </div>
      </template>

      <!-- ── 消息区 ───────────────────────────────────── -->
      <div ref="scrollBox" class="msg-box">
        <div v-if="!messages.length && !answering" class="msg-empty">
          <el-icon class="empty-icon"><ChatLineRound /></el-icon>
          <div class="empty-title">劳动法智能咨询</div>
          <div class="empty-sub">
            免费咨询试用期、竞业限制、离职赔偿等劳动法问题，回答会引用法条原文。
            可先做一份合同分析，再把问题关联到对应报告。
          </div>
        </div>

        <template v-for="(m, idx) in messages" :key="m.id || idx">
          <!-- 用户消息: 右侧气泡 -->
          <div v-if="m.role === 'user'" class="msg-row user">
            <div class="bubble user-bubble">{{ m.content }}</div>
          </div>
          <!-- 助手消息: 左侧气泡 -->
          <div v-else class="msg-row assistant">
            <div class="bubble assistant-bubble">
              <div v-if="m.references?.length" class="ref-chips">
                <el-tag
                  v-for="(r, ri) in m.references"
                  :key="ri"
                  size="small"
                  type="primary"
                  effect="plain"
                  class="ref-chip"
                  @click="openRefDialog(r)"
                >
                  [{{ ri + 1 }}] {{ r.law_name }}·{{ r.article }}
                </el-tag>
              </div>
              <div class="msg-content">{{ renderContent(m.content) }}</div>
              <div v-if="m.suggestions?.length" class="sugg-chips">
                <el-tag
                  v-for="(sg, si) in m.suggestions"
                  :key="si"
                  size="small"
                  class="sugg-chip"
                  @click="sendSuggestion(sg)"
                >
                  {{ sg }}
                </el-tag>
              </div>
            </div>
          </div>
        </template>

        <!-- 作答中: 步骤 + 打字气泡 -->
        <div v-if="answering" class="msg-row assistant">
          <div class="bubble assistant-bubble">
            <div class="thinking">{{ latestStep }}</div>
            <span class="dots">正在回答</span>
          </div>
        </div>
      </div>

      <!-- ── 底栏: 输入区 ────────────────────────────── -->
      <div class="input-bar">
        <div class="input-main">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="1"
            autosize
            resize="none"
            placeholder="输入你的劳动法问题，Enter 发送，Shift+Enter 换行"
            :disabled="answering"
            maxlength="2000"
            show-word-limit
            @keydown.enter.exact.prevent="send"
          />
          <!-- 意图识别: 输入框下方实时显示 -->
          <div
            v-if="intentLoading || (intentResult && intentResult.intent !== 'unknown')"
            class="intent-hint"
          >
            <span v-if="intentLoading && !intentResult" class="intent-loading">正在识别意图…</span>
            <template v-else-if="intentResult">
              <el-tag size="small" :type="intentTagType" effect="plain">{{ intentResult.label }}</el-tag>
              <span class="intent-conf">置信度 {{ Math.round(intentResult.confidence * 100) }}%</span>
              <span class="intent-method">· {{ intentResult.method === 'llm' ? '模型判定' : '规则判定' }}</span>
            </template>
          </div>
        </div>
        <el-button
          type="primary"
          class="send-btn"
          :loading="answering"
          :disabled="!draft.trim() || answering"
          @click="send"
        >
          发送
        </el-button>
      </div>
    </el-card>

    <!-- ── 法条全文对话框 ────────────────────────────── -->
    <el-dialog
      v-model="refDialogVisible"
      :title="refDialogTitle"
      width="640px"
      append-to-body
    >
      <div class="ref-body">{{ refDialogContent }}</div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatLineRound } from '@element-plus/icons-vue'
import { contractApi, type ContractListItem } from '@/api/contract'
import {
  askConsult,
  consultApi,
  type ConsultMessage,
  type ConsultRef,
  type IntentResult,
} from '@/api/consult'
import { formatTime } from '@/utils/contractMeta'
import { useConsultStore } from '@/stores/consult'

const route = useRoute()
const router = useRouter()
const consult = useConsultStore()

// 当前会话 ID: 以 URL ?s=xxx 为唯一真相, 由 watcher 与侧栏点击共同维护
const sessionSel = ref<string | null>(null)
const contracts = ref<ContractListItem[]>([])
const contractSel = ref<string | null>(null)

const messages = ref<ConsultMessage[]>([])
const draft = ref('')
const answering = ref(false)
const steps = ref<string[]>([])
let abortCtrl: AbortController | null = null

// ── 意图识别 (输入框下方实时提示) ────────────────────
const intentResult = ref<IntentResult | null>(null)
const intentLoading = ref(false)
/** 意图 → 标签配色; 未登记的意图统一走 info */
const INTENT_TAG_TYPES: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  law_query: 'success',
  clause_explain: 'info',
  risk_analysis: 'danger',
  negotiation: 'warning',
  procedure: 'warning',
  chitchat: 'info',
}
const intentTagType = computed(
  () => INTENT_TAG_TYPES[intentResult.value?.intent ?? ''] ?? 'info'
)

const _INTENT_MIN_LEN = 2 // 少于 2 个字不识别, 避免输入过程中的噪音请求
const _INTENT_DEBOUNCE = 400 // ms, 停止输入后再请求
let intentTimer: ReturnType<typeof setTimeout> | null = null
let intentSeq = 0 // 请求序号: 后发请求覆盖先发请求, 丢弃过期响应

const clearIntentTimer = () => {
  if (intentTimer !== null) {
    clearTimeout(intentTimer)
    intentTimer = null
  }
}

/** 丢弃在途请求并清空提示 (输入清空 / 发送后) */
const resetIntent = () => {
  clearIntentTimer()
  intentSeq++
  intentResult.value = null
  intentLoading.value = false
}

const runIntent = async (question: string) => {
  const seq = ++intentSeq
  intentLoading.value = true
  try {
    const { data } = await consultApi.intent(question)
    if (seq !== intentSeq) return // 已有更新的输入, 丢弃本次结果
    intentResult.value = data
  } catch {
    if (seq === intentSeq) intentResult.value = null // 静默失败, 不打扰用户
  } finally {
    if (seq === intentSeq) intentLoading.value = false
  }
}

watch(draft, (val) => {
  clearIntentTimer()
  const q = (val || '').trim()
  if (q.length < _INTENT_MIN_LEN || answering.value) {
    resetIntent()
    return
  }
  intentSeq++ // 使在途请求失效
  intentResult.value = null // 旧结论已不适用, 立刻进入「识别中」
  intentLoading.value = true
  intentTimer = setTimeout(() => {
    intentTimer = null
    if (answering.value) {
      intentLoading.value = false
      return
    }
    runIntent(q)
  }, _INTENT_DEBOUNCE)
})

const refDialogVisible = ref(false)
const refDialogTitle = ref('')
const refDialogContent = ref('')

const scrollBox = ref<HTMLElement | null>(null)
const latestStep = computed(
  () => steps.value[steps.value.length - 1] ?? '正在思考…'
)

const previewLabel = (p: string) => {
  const flat = (p || '').replace(/\s+/g, ' ')
  return flat.length > 20 ? `${flat.slice(0, 20)}…` : flat || '合同报告'
}

const scrollDown = async () => {
  await nextTick()
  const el = scrollBox.value
  if (el) el.scrollTop = el.scrollHeight
}

// ── 数据加载 ────────────────────────────────────────
const fetchContracts = async () => {
  try {
    const { data } = await contractApi.list({ status: 'completed', page_size: 100 })
    contracts.value = data.items
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '报告列表加载失败')
  }
}

/** 按 ID 加载一次会话的完整消息; 找不到(可能尚未在列表中)也直接拉接口 */
const loadMessages = async (sessionId: string) => {
  try {
    const { data } = await consultApi.messages(sessionId)
    messages.value = data
    const cur = consult.sessions.find((s) => s.id === sessionId)
    contractSel.value = cur?.contract_id ?? null
    await scrollDown()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '消息记录加载失败')
  }
}

// ── 会话切换: 由 URL ?s= 驱动 ──────────────────────
// 标志: 防止在「自己刚更新 URL」时 watcher 反向触发重置/重新拉取
let suppressWatcher = false

const switchToSession = async (id: string) => {
  answering.value = false
  abortCtrl?.abort()
  steps.value = []
  sessionSel.value = id
  await loadMessages(id)
}

const resetChat = () => {
  answering.value = false
  abortCtrl?.abort()
  abortCtrl = null
  steps.value = []
  sessionSel.value = null
  contractSel.value = null
  messages.value = []
  draft.value = ''
}

const startNewChat = () => {
  // 顶部「新对话」按钮: 跳到 /consult 干净地址, 由 watcher 触发重置
  router.push({ path: '/consult' })
}

// 监听 URL 中的会话 ID, 侧栏切换会通过此机制反映到页面
watch(
  () => route.query.s,
  async (s) => {
    if (suppressWatcher) { suppressWatcher = false; return }
    if (typeof s === 'string' && s) {
      if (s !== sessionSel.value) await switchToSession(s)
    } else {
      if (sessionSel.value !== null || messages.value.length) resetChat()
    }
  }
)

/** 工具栏上显示的「当前会话」标题, 为空表示新对话 */
const currentSessionTitle = computed(() => {
  if (!sessionSel.value) return ''
  return consult.sessions.find((s) => s.id === sessionSel.value)?.title || '历史会话'
})

// ── 发送与事件处理 ──────────────────────────────────
const send = async () => {
  const question = draft.value.trim()
  if (!question || answering.value) return
  messages.value.push({
    id: `local-${Date.now()}`,
    role: 'user',
    content: question,
    references: null,
    suggestions: null,
    created_at: '',
  })
  draft.value = ''
  answering.value = true
  steps.value = []
  await scrollDown()

  abortCtrl = new AbortController()
  try {
    await askConsult(
      {
        question,
        session_id: sessionSel.value,
        contract_id: contractSel.value,
      },
      handleEvent,
      abortCtrl.signal
    )
  } catch (e: any) {
    if (e?.name === 'AbortError') return
    answering.value = false
    ElMessage.error(e?.message || '咨询失败，请稍后重试')
  } finally {
    if (answering.value) answering.value = false
    abortCtrl = null
  }
}

const handleEvent = (type: string, data: any) => {
  switch (type) {
    case 'session':
      // 后端告知本轮属于哪个会话, 把 URL 同步过去(便于刷新/分享/侧栏高亮)
      suppressWatcher = true
      sessionSel.value = data.session_id
      router.replace({ path: '/consult', query: { s: data.session_id } })
      consult.fetchSessions()
      break
    case 'step':
      steps.value.push(data.message)
      scrollDown()
      break
    case 'answer':
      messages.value.push({
        id: data.message_id,
        role: 'assistant',
        content: data.content,
        references: data.references ?? null,
        suggestions: data.suggestions ?? null,
        created_at: '',
      })
      scrollDown()
      break
    case 'complete':
      answering.value = false
      consult.fetchSessions()
      break
    case 'error':
      answering.value = false
      messages.value.push({
        id: `local-${Date.now()}`,
        role: 'assistant',
        content: data.message ?? '回答失败，请稍后重试',
        references: null,
        suggestions: null,
        created_at: '',
      })
      consult.fetchSessions()
      scrollDown()
      break
  }
}

const sendSuggestion = async (text: string) => {
  if (answering.value) return
  draft.value = text
  await send()
}

// ── 法条引用对话框 ──────────────────────────────────
const openRefDialog = (ref: ConsultRef) => {
  refDialogTitle.value = `${ref.law_name} ${ref.article}`
  refDialogContent.value = ref.content
  refDialogVisible.value = true
}

/** 轻量排版: 仅去掉 Markdown 粗体/标题记号, 不做 HTML 渲染 */
const renderContent = (s: string) =>
  s.replace(/\*\*(.+?)\*\*/g, '$1').replace(/^#+\s*/gm, '')

onMounted(async () => {
  await Promise.all([consult.fetchSessions(), fetchContracts()])
  // 初始会话: 如果 URL 带了 ?s=, 加载之; 否则保持「新对话」空状态
  const s = route.query.s
  if (typeof s === 'string' && s) {
    await switchToSession(s)
  }
})

onBeforeUnmount(() => {
  abortCtrl?.abort()
  clearIntentTimer()
})
</script>

<style scoped>
.consult {
  height: calc(100vh - 100px);
  min-height: 460px;
}
.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.chat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 14px 20px 16px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.contract-sel {
  width: 280px;
}
.toolbar-sep {
  width: 1px;
  height: 18px;
  background: #ebeef5;
  margin: 0 2px;
}
.toolbar-label {
  font-size: 13px;
  color: #606266;
  flex-shrink: 0;
}
.hint {
  font-size: 12px;
  color: #409eff;
}
.current-session {
  font-size: 12px;
  color: #909399;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.msg-box {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
}
.msg-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}
.empty-icon {
  font-size: 46px;
  color: #c0c4cc;
}
.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #606266;
}
.empty-sub {
  max-width: 460px;
  font-size: 13px;
  color: #909399;
  line-height: 1.7;
}
.msg-row {
  display: flex;
  margin-bottom: 14px;
}
.msg-row.user {
  justify-content: flex-end;
}
.msg-row.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}
.user-bubble {
  background: #409eff;
  color: #ffffff;
  border-top-right-radius: 2px;
}
.assistant-bubble {
  background: #ffffff;
  border: 1px solid #ebeef5;
  border-top-left-radius: 2px;
  color: #303133;
}
.ref-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.ref-chip {
  cursor: pointer;
}
.msg-content {
  white-space: pre-wrap;
}
.sugg-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e4e7ed;
}
.sugg-chip {
  cursor: pointer;
}
.thinking {
  color: #909399;
  font-size: 13px;
}
.dots {
  color: #909399;
  font-size: 13px;
}
.input-bar {
  display: flex;
  /* 顶对齐: 输入框下方多了意图提示行, 按钮需与首行输入框对齐 */
  align-items: flex-start;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid #f0f2f5;
}
.input-main {
  flex: 1;
  min-width: 0;
}
.input-main :deep(.el-textarea__inner) {
  line-height: 1.6;
}
/* 意图提示: 输入框下方一行, 不占额外高度时自动隐藏 */
.intent-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 20px;
  margin-top: 4px;
  padding-left: 2px;
  font-size: 12px;
  color: #909399;
  line-height: 20px;
}
.intent-loading {
  color: #c0c4cc;
}
.intent-conf {
  color: #909399;
}
.intent-method {
  color: #c0c4cc;
}
.send-btn {
  width: 84px;
}
.ref-body {
  white-space: pre-wrap;
  line-height: 1.9;
  color: #303133;
  max-height: 60vh;
  overflow-y: auto;
}
</style>
