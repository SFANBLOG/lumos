<template>
  <div class="mcp">
    <el-card shadow="never">
      <template #header>
        <div class="mcp-head">
          <span class="card-title">MCP 工具工作台</span>
          <div class="head-actions">
            <span class="head-sub">工具由后端子智能体注册，可直接调用体验</span>
            <el-button :icon="Refresh" circle plain @click="fetchTools" />
          </div>
        </div>
      </template>

      <el-table :data="tools" v-loading="loading" empty-text="暂无工具">
        <el-table-column prop="name" label="工具名" width="150">
          <template #default="{ row }">
            <span class="tool-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" />
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openCall(row)">调用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ── 调用对话框: 按 input_schema 动态生成表单 ─────── -->
    <el-dialog v-model="dialogVisible" :title="`调用 ${activeTool?.name ?? ''}`" width="560px" append-to-body>
      <template v-if="activeTool">
        <div class="tool-desc">{{ activeTool.description }}</div>
        <el-form v-if="propKeys.length" label-position="top">
          <el-form-item
            v-for="key in propKeys"
            :key="key"
            :label="propLabel(key)"
            :required="isRequired(key)"
          >
            <!-- 枚举选择 -->
            <el-select
              v-if="isEnum(key)"
              v-model="formArgs[key]"
              :placeholder="`选择 ${propLabel(key)}`"
              clearable
            >
              <el-option v-for="v in enumOptions(key)" :key="v" :value="v" :label="enumLabel(v)" />
            </el-select>
            <!-- 多选枚举 (数组) -->
            <el-select
              v-else-if="isArrayEnum(key)"
              v-model="formArgs[key]"
              multiple
              collapse-tags
              :placeholder="`可多选 ${propLabel(key)}`"
            >
              <el-option v-for="v in enumOptions(key)" :key="v" :value="v" :label="enumLabel(v)" />
            </el-select>
            <!-- 整数 -->
            <el-input-number
              v-else-if="propType(key) === 'integer'"
              v-model="formArgs[key]"
              :min="propMin(key)"
              :max="propMax(key)"
            />
            <!-- 字符串 -->
            <el-input v-else v-model="formArgs[key]" :placeholder="schemaProp(key)?.description || ''" />
          </el-form-item>
        </el-form>
        <el-alert v-else title="该工具无需参数，直接调用即可" type="info" :closable="false" />

        <el-alert
          v-if="callResult !== null"
          :title="callError ? '调用失败' : '调用成功'"
          :type="callError ? 'error' : 'success'"
          :closable="false"
          class="result-alert"
        >
          <template #default>
            <pre class="result-json">{{ callResult }}</pre>
          </template>
        </el-alert>
      </template>

      <template #footer>
        <el-button :disabled="calling" @click="dialogVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="calling"
          :disabled="!formValid"
          @click="doCall"
        >
          执行
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import apiClient from '@/api/client'
import { categoryLabel } from '@/utils/contractMeta'

interface SchemaProp {
  type?: string
  description?: string
  enum?: string[]
  default?: number | string
  minimum?: number
  maximum?: number
  items?: { type?: string; enum?: string[] }
}
interface InputSchema {
  type?: string
  properties?: Record<string, SchemaProp>
  required?: string[]
}
interface MCPTool {
  name: string
  description: string
  input_schema?: InputSchema
}

const tools = ref<MCPTool[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const activeTool = ref<MCPTool | null>(null)
const formArgs = ref<Record<string, any>>({})
const calling = ref(false)
const callResult = ref<string | null>(null)
const callError = ref(false)

const schemaProps = computed(() => activeTool.value?.input_schema?.properties ?? {})
const requiredList = computed(() => activeTool.value?.input_schema?.required ?? [])
const propKeys = computed(() => Object.keys(schemaProps.value))

const schemaProp = (key: string): SchemaProp | undefined => schemaProps.value[key]
const propType = (key: string) => schemaProp(key)?.type ?? 'string'
const isRequired = (key: string) => requiredList.value.includes(key)
const isEnum = (key: string) =>
  propType(key) === 'string' && !!schemaProp(key)?.enum?.length
const isArrayEnum = (key: string) =>
  propType(key) === 'array' && !!schemaProp(key)?.items?.enum?.length
const enumOptions = (key: string) => {
  const p = schemaProp(key)
  return p?.type === 'array' ? (p.items?.enum ?? []) : (p?.enum ?? [])
}
const propMin = (key: string) => schemaProp(key)?.minimum ?? 0
const propMax = (key: string) => schemaProp(key)?.maximum ?? 100
const propLabel = (key: string) => {
  const zh = keyLabels[key]
  return zh ?? key
}
const enumLabel = (v: string) => {
  if (categoryLabels.has(v)) return `${categoryLabel(v)} (${v})`
  return v
}

const keyLabels: Record<string, string> = {
  query: '检索问题',
  top_k: '返回条数',
  category: '风险分类',
  categories: '风险分类',
  total_clauses: '总条款数',
  clause_title: '条款标题',
  clause_content: '条款内容',
}
const categoryLabels = new Set([
  'non_compete',
  'probation_salary',
  'probation_insurance',
  'salary_deduction',
  'job_description',
  'obedience_clause',
  'resignation',
  'leave_rights',
  'jurisdiction',
  'training_bond',
])

const formValid = computed(() => {
  if (!activeTool.value) return false
  return requiredList.value.every((key) => {
    const v = formArgs.value[key]
    if (v === undefined || v === null || v === '') return false
    if (Array.isArray(v)) return v.length > 0
    return true
  })
})

const fetchTools = async () => {
  loading.value = true
  try {
    const { data } = await apiClient.get('/mcp/tools')
    tools.value = data
  } finally {
    loading.value = false
  }
}

const openCall = (tool: MCPTool) => {
  activeTool.value = tool
  formArgs.value = {}
  const props = tool.input_schema?.properties ?? {}
  Object.entries(props).forEach(([key, p]) => {
    if (p.default !== undefined) formArgs.value[key] = p.default
    else if (p.type === 'array') formArgs.value[key] = []
  })
  callResult.value = null
  callError.value = false
  dialogVisible.value = true
}

const buildArgs = (): Record<string, any> => {
  const args: Record<string, any> = {}
  Object.entries(formArgs.value).forEach(([key, v]) => {
    if (v === undefined || v === null || v === '') return
    args[key] = v
  })
  return args
}

const doCall = async () => {
  if (!activeTool.value || !formValid.value) return
  calling.value = true
  callResult.value = null
  callError.value = false
  try {
    const { data } = await apiClient.post('/mcp/tools/call', {
      tool_name: activeTool.value.name,
      arguments: buildArgs(),
    })
    callResult.value = JSON.stringify(data, null, 2)
  } catch (e: any) {
    callError.value = true
    const detail = e.response?.data?.detail
    callResult.value =
      typeof detail === 'string' || detail === undefined
        ? detail ?? e.message ?? '调用失败'
        : JSON.stringify(detail, null, 2)
  } finally {
    calling.value = false
  }
}

onMounted(fetchTools)
</script>

<style scoped>
.mcp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-title {
  font-weight: 600;
  color: #303133;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.head-sub {
  font-size: 12px;
  color: #909399;
}
.tool-name {
  font-weight: 500;
  color: #303133;
}
.tool-desc {
  color: #606266;
  font-size: 13px;
  margin-bottom: 14px;
}
.result-alert {
  margin-top: 16px;
}
.result-json {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.6;
  max-height: 260px;
  overflow-y: auto;
}
</style>
