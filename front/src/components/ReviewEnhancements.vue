<template>
  <div v-if="facts.length || clauses.length" class="enhance-box">
    <div class="enhance-head">
      <span class="enhance-title">审查增强</span>
      <span class="enhance-coverage" :class="{ 'is-low': coverage < 70 }">
        必备条款覆盖率 {{ coverage }}%
      </span>
    </div>

    <el-collapse v-model="opened">
      <el-collapse-item name="facts">
        <template #title>
          合同要素核对表 <span class="enhance-count">{{ presentCount }}/{{ facts.length }}</span>
        </template>
        <div v-for="fact in facts" :key="fact.key" class="fact-row">
          <span class="fact-mark" :class="fact.status === 'present' ? 'ok' : 'miss'">
            {{ fact.status === 'present' ? '✓' : '!' }}
          </span>
          <span class="fact-label">{{ fact.label }}</span>
          <span class="fact-value" :title="fact.evidence">
            {{ fact.value || (fact.required ? '未检出（必备）' : '未检出') }}
          </span>
        </div>
        <p v-if="!facts.length" class="enhance-empty">暂无要素数据</p>
      </el-collapse-item>

      <el-collapse-item name="missing">
        <template #title>
          缺失条款与建议补充 <span class="enhance-count warn">{{ clauses.length }} 项</span>
        </template>
        <div v-for="item in clauses" :key="item.key" class="missing-row">
          <div class="missing-title">{{ item.label }}</div>
          <div class="missing-reason">{{ item.reason }}</div>
          <div class="missing-suggest">建议补充：{{ item.suggested_text }}</div>
          <div v-if="item.legal_basis" class="missing-basis">{{ item.legal_basis }}</div>
        </div>
        <p v-if="!clauses.length" class="enhance-empty">未检出必备条款缺失</p>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ContractFactData, MissingClauseData } from '@/api/contract'

const props = defineProps<{
  facts: ContractFactData[]
  clauses: MissingClauseData[]
  coverage: number
}>()

const opened = ref<string[]>(['missing'])
const presentCount = computed(() => props.facts.filter((f) => f.status === 'present').length)
</script>

<style scoped>
.enhance-box {
  border: 1px solid var(--qz-line);
  border-radius: 10px;
  background: #fafbff;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.enhance-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.enhance-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink-1);
}
.enhance-coverage {
  font-size: 12px;
  color: #1a7f4b;
  background: #eaf7ef;
  border-radius: 999px;
  padding: 2px 9px;
}
.enhance-coverage.is-low {
  color: #b45309;
  background: #fff4e5;
}
.enhance-count {
  margin-left: 8px;
  font-size: 12px;
  color: var(--qz-ink-3);
}
.enhance-count.warn {
  color: #b45309;
}
.fact-row {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px dashed var(--qz-line);
}
.fact-mark {
  flex-shrink: 0;
  width: 15px;
  text-align: center;
  font-weight: 700;
}
.fact-mark.ok { color: #1a7f4b; }
.fact-mark.miss { color: #d97706; }
.fact-label {
  flex-shrink: 0;
  width: 108px;
  color: var(--qz-ink-2);
}
.fact-value {
  flex: 1;
  min-width: 0;
  color: var(--qz-ink-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.missing-row {
  padding: 8px 0;
  border-bottom: 1px dashed var(--qz-line);
  font-size: 12px;
}
.missing-title {
  font-weight: 600;
  color: var(--qz-ink-1);
  margin-bottom: 3px;
}
.missing-reason { color: var(--qz-ink-2); }
.missing-suggest {
  margin-top: 4px;
  color: #1d4ed8;
  background: #eef4ff;
  border-radius: 6px;
  padding: 5px 7px;
  line-height: 1.5;
}
.missing-basis {
  margin-top: 3px;
  font-size: 11px;
  color: var(--qz-ink-3);
}
.enhance-empty {
  font-size: 12px;
  color: var(--qz-ink-3);
  margin: 4px 0;
}
</style>
