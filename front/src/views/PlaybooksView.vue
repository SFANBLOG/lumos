<template>
  <div class="page" v-loading="loading"><section class="page-head"><div><span class="eyebrow">POLICY AS CODE</span><h1>审查 Playbook</h1><p>把团队的审查口径写成 Agent 可执行、可追溯的标准。</p></div><el-tag type="success" effect="light">{{ playbook?.status === 'active' ? '当前启用' : '加载中' }}</el-tag></section><el-card v-if="playbook" shadow="never"><div class="meta"><div><small>审查基线</small><h2>{{ playbook.name }}</h2></div><div><small>版本</small><strong>{{ playbook.version }}</strong></div><div><small>立场</small><strong>{{ playbook.position === 'employee_friendly' ? '劳动者权益优先' : playbook.position }}</strong></div></div><el-divider>执行规则</el-divider><ol class="rules"><li v-for="(rule, index) in playbook.rules" :key="rule"><b>{{ String(index + 1).padStart(2, '0') }}</b><span>{{ rule }}</span></li></ol><div class="note">此版本为工作区当前生效的基线。自定义规则、版本审批与发布流程将建立在此基础上。</div></el-card></div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi, type Playbook } from '@/api/agent'
import { apiErrorMessage } from '@/api/client'

const playbook = ref<Playbook | null>(null)
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    playbook.value = (await agentApi.activePlaybook()).data
  } catch (e) {
    ElMessage.error(apiErrorMessage(e, '审查标准加载失败'))
  } finally {
    loading.value = false
  }
})
</script>
<style scoped>.page{max-width:1000px;margin:0 auto}.page-head{background:linear-gradient(125deg,#10233f,#1b477e);color:#fff;padding:26px 30px;margin-bottom:16px;border-radius:12px;display:flex;justify-content:space-between;align-items:start}.eyebrow{font-size:11px;letter-spacing:1.4px;color:#9fc0ff}.page-head h1{margin:6px 0;font-size:25px}.page-head p{margin:0;color:#cbd9f2}.meta{display:flex;gap:56px;padding:6px 4px 14px}.meta div{display:grid;gap:6px}.meta small{color:#8795a7}.meta h2{margin:0;font-size:21px}.meta strong{color:#24364c}.rules{list-style:none;padding:0;margin:8px 0}.rules li{display:flex;gap:18px;padding:17px 8px;border-bottom:1px solid #edf1f6;line-height:1.7}.rules b{color:#1f5eff;letter-spacing:1px}.note{margin-top:22px;background:#f3f7ff;border-radius:8px;padding:14px;color:#52657e;font-size:13px}</style>
