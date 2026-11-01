<template>
  <div v-if="check" class="doc-check" :class="{ 'doc-check--blocked': !check.is_contract }">
    <span class="doc-check__label">内容识别</span>
    <el-tag size="small" :type="check.is_contract ? 'success' : 'warning'" effect="plain">
      {{ check.doc_type_label }}
    </el-tag>
    <span class="doc-check__meta">置信度 {{ percent }}%</span>
    <span class="doc-check__meta">· {{ methodText }}</span>
    <div v-if="check.notice" class="doc-check__notice">{{ check.notice }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DocCheck } from '@/api/ingest'

const props = defineProps<{ check?: DocCheck | null }>()

const METHOD_TEXT: Record<string, string> = {
  rule: '规则判定',
  llm: '模型判定',
  ext: '文件类型判定',
}

const percent = computed(() => Math.round((props.check?.confidence ?? 0) * 100))
const methodText = computed(() => METHOD_TEXT[props.check?.method ?? ''] ?? '规则判定')
</script>

<style scoped>
.doc-check {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  padding: 7px 10px;
  border: 1px solid var(--qz-line);
  border-radius: 8px;
  background: #fafbfe;
  font-size: 12px;
  color: var(--qz-muted);
}

.doc-check--blocked {
  border-color: #f6e2b8;
  background: var(--qz-warn-soft);
}

.doc-check__label {
  font-size: 12px;
  color: #606266;
}

.doc-check__meta {
  color: var(--qz-muted);
}

.doc-check__notice {
  flex: 0 0 100%;
  line-height: 1.6;
  color: #8a6d3b;
}

.doc-check--blocked .doc-check__notice {
  color: #9a6b09;
}
</style>
