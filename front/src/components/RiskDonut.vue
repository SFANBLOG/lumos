<template>
  <div class="donut-wrap">
    <svg viewBox="0 0 220 220" class="donut" role="img" :aria-label="`风险总数 ${totalCount}`">
      <circle cx="110" cy="110" :r="R" fill="none" stroke="#f4f5fa" :stroke-width="STROKE" />
      <circle
        v-for="(segment, index) in segments"
        :key="index"
        cx="110"
        cy="110"
        :r="R"
        fill="none"
        :stroke="segment.color"
        :stroke-width="STROKE"
        :stroke-dasharray="`${segment.length} ${CIRC - segment.length}`"
        :stroke-dashoffset="-segment.offset"
        stroke-linecap="butt"
        transform="rotate(-90 110 110)"
        class="segment"
      >
        <title>{{ segment.label }}：{{ segment.value }}</title>
      </circle>
      <text x="110" y="104" text-anchor="middle" class="donut-total">{{ totalCount }}</text>
      <text x="110" y="126" text-anchor="middle" class="donut-cap">{{ caption }}</text>
    </svg>

    <div v-if="showLegend" class="donut-legend">
      <div v-for="item in items" :key="item.label" class="legend-row">
        <span class="legend-dot" :style="{ background: item.color }" />
        <span class="legend-label">{{ item.label }}</span>
        <strong class="legend-value">{{ item.value }}</strong>
        <span class="legend-pct">{{ percent(item.value) }}%</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface DonutItem {
  label: string
  value: number
  color: string
}

const props = withDefaults(
  defineProps<{
    items: DonutItem[]
    total?: number
    caption?: string
    showLegend?: boolean
  }>(),
  { total: 0, caption: '风险总数', showLegend: true }
)

const R = 78
const STROKE = 22
const CIRC = 2 * Math.PI * R

const sum = computed(() => props.items.reduce((acc, item) => acc + item.value, 0))
const totalCount = computed(() => props.total || sum.value)
const segments = computed(() => {
  const denominator = sum.value || 1
  let offset = 0
  return props.items.map((item) => {
    const length = (item.value / denominator) * CIRC
    const segment = { ...item, length, offset }
    offset += length
    return segment
  })
})

const percent = (value: number) => {
  const denominator = sum.value || 1
  return ((value / denominator) * 100).toFixed(1)
}
</script>

<style scoped>
.donut-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.donut {
  width: 196px;
  height: 196px;
}
.segment {
  transition: stroke-dasharray 0.6s ease;
}
.donut-total {
  font-size: 30px;
  font-weight: 700;
  fill: var(--qz-ink);
  font-family: Inter, "PingFang SC", sans-serif;
}
.donut-cap {
  font-size: 11px;
  fill: #9aa0b3;
  font-family: Inter, "PingFang SC", sans-serif;
}
.donut-legend {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin-top: 2px;
}
.legend-row {
  display: grid;
  grid-template-columns: 8px 1fr auto 44px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.legend-label {
  color: var(--qz-ink-2);
}
.legend-value {
  color: var(--qz-ink);
  font-weight: 650;
}
.legend-pct {
  text-align: right;
  color: var(--qz-muted);
}
</style>
