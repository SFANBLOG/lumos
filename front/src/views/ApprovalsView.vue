<template>
  <div class="page" v-loading="loading">
    <section class="page-head"><div><span class="eyebrow">HUMAN-IN-THE-LOOP</span><h1>人工审批队列</h1><p>高风险结论须经授权人员确认；每一次决定都会被保留在审计记录中。</p></div><el-button @click="fetchTasks">刷新队列</el-button></section>
    <el-card shadow="never"><div class="filter"><el-radio-group v-model="filter" @change="fetchTasks"><el-radio-button label="">全部</el-radio-button><el-radio-button label="pending">待处理</el-radio-button><el-radio-button label="approved">已通过</el-radio-button><el-radio-button label="rejected">已驳回</el-radio-button></el-radio-group></div>
      <el-table :data="tasks" empty-text="当前没有需要处理的审批事项"><el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="tagType(row.status)">{{ label(row.status) }}</el-tag></template></el-table-column><el-table-column label="合同摘要" min-width="360"><template #default="{ row }"><div class="preview">{{ row.contract_preview }}</div><small>{{ formatTime(row.created_at) }}</small></template></el-table-column><el-table-column label="审批意见" min-width="180"><template #default="{ row }">{{ row.comment || '—' }}</template></el-table-column><el-table-column label="操作" width="140"><template #default="{ row }"><el-button v-if="row.status === 'pending' && row.can_decide" link type="primary" @click="openDecision(row)">处理</el-button><el-button v-else link type="primary" @click="openReport(row.contract_id)">查看报告</el-button></template></el-table-column></el-table>
    </el-card>
    <el-dialog v-model="dialog" title="提交审批决定" width="460px"><el-radio-group v-model="decision"><el-radio label="approved">通过</el-radio><el-radio label="rejected">驳回</el-radio></el-radio-group><el-input v-model="comment" class="comment" type="textarea" :rows="4" maxlength="1000" show-word-limit placeholder="填写决定依据，供申请人与审计人员追溯" /><template #footer><el-button @click="dialog=false">取消</el-button><el-button type="primary" :loading="submitting" @click="submitDecision">确认决定</el-button></template></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { agentApi, type ApprovalStatus, type ApprovalTask } from '@/api/agent'
import { apiErrorMessage } from '@/api/client'
const router = useRouter(); const tasks = ref<ApprovalTask[]>([]); const loading = ref(false); const filter = ref(''); const dialog = ref(false); const target = ref<ApprovalTask | null>(null); const decision = ref<'approved'|'rejected'>('approved'); const comment = ref(''); const submitting = ref(false)
const fetchTasks = async () => { loading.value = true; try { tasks.value = (await agentApi.approvals(filter.value as ApprovalStatus || undefined)).data } catch(e) { ElMessage.error(apiErrorMessage(e, '审批队列加载失败')) } finally { loading.value = false } }
const label = (v: ApprovalStatus) => ({ pending:'待处理', approved:'已通过', rejected:'已驳回' }[v]); const tagType = (v: ApprovalStatus) => v === 'approved' ? 'success' : v === 'rejected' ? 'danger' : 'warning'; const formatTime = (v:string) => new Date(v).toLocaleString('zh-CN', { hour12:false })
const openDecision = (task: ApprovalTask) => { target.value = task; decision.value = 'approved'; comment.value = ''; dialog.value = true }; const openReport = (id:string) => router.push({ path:'/reports', query:{ open:id } })
const submitDecision = async () => { if (!target.value) return; submitting.value=true; try { await agentApi.decide(target.value.id, decision.value, comment.value); ElMessage.success('审批决定已记录'); dialog.value=false; fetchTasks() } catch(e) { ElMessage.error(apiErrorMessage(e, '审批提交失败')) } finally { submitting.value=false } }
onMounted(fetchTasks)
</script>
<style scoped>
.page{max-width:1200px;margin:0 auto}.page-head{display:flex;justify-content:space-between;align-items:flex-end;background:#fff;padding:24px 26px;margin-bottom:16px;border:1px solid #e7edf6;border-radius:12px}.eyebrow{font-size:11px;letter-spacing:1.4px;color:#1f5eff}.page-head h1{margin:6px 0;font-size:24px}.page-head p{margin:0;color:#66758b}.filter{margin-bottom:16px}.preview{color:#29384d;line-height:1.6}.preview+small{color:#94a3b8}.comment{margin-top:18px}
</style>
