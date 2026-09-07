<template>
  <div class="analysis">
    <el-page-header title="返回" @back="$router.push('/')" />
    <h2>合同风险排查</h2>

    <el-input
      v-model="text"
      type="textarea"
      :rows="10"
      placeholder="请将劳动合同全文粘贴到这里..."
      :disabled="analyzing"
    />

    <div class="toolbar">
      <el-button type="primary" :loading="analyzing" @click="startAnalysis" :disabled="!text.trim()">
        开始分析
      </el-button>
    </div>

    <div v-if="statusMessage" class="status">{{ statusMessage }}</div>
    <el-progress v-if="analyzing" :percentage="Math.round(progress * 100)" />

    <div v-if="risks.length" class="risks">
      <h3>发现 {{ risks.length }} 项风险</h3>
      <el-collapse>
        <el-collapse-item v-for="(risk, idx) in risks" :key="idx" :title="risk.title">
          <p><strong>风险等级：</strong>{{ risk.level }}</p>
          <p><strong>原始条文：</strong>{{ risk.original_clause }}</p>
          <p><strong>大白话解读：</strong>{{ risk.explanation }}</p>
          <p><strong>法律依据：</strong>{{ risk.legal_basis }}</p>
          <p><strong>谈判话术：</strong>{{ risk.negotiation_tip }}</p>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { contractApi } from '@/api/contract'

const text = ref('')
const analyzing = ref(false)
const progress = ref(0)
const statusMessage = ref('')
const risks = ref<any[]>([])
let eventSource: EventSource | null = null

const startAnalysis = async () => {
  if (!text.value.trim()) return
  analyzing.value = true
  progress.value = 0
  statusMessage.value = '正在提交合同...'
  risks.value = []

  try {
    const { data } = await contractApi.submit({ text: text.value, source: 'text_paste' })
    statusMessage.value = data.message
    eventSource = contractApi.stream(data.contract_id, (event) => handleEvent(event))
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '分析失败')
    analyzing.value = false
  }
}

const handleEvent = (event: { event: string; data: any }) => {
  if (event.event === 'node_start' || event.event === 'node_complete') {
    statusMessage.value = event.data.description
    progress.value = event.data.progress
  } else if (event.event === 'risk_found') {
    risks.value.push(event.data)
  } else if (event.event === 'summary') {
    statusMessage.value = event.data.summary
  } else if (event.event === 'complete') {
    statusMessage.value = '分析完成'
    analyzing.value = false
    eventSource?.close()
  } else if (event.event === 'error') {
    statusMessage.value = event.data.message
    analyzing.value = false
    eventSource?.close()
  }
}
</script>

<style scoped>
.analysis {
  padding: 24px;
}
.toolbar {
  margin-top: 16px;
}
.status {
  margin: 16px 0;
  color: #606266;
}
.risks {
  margin-top: 24px;
}
</style>
