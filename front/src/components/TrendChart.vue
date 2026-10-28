<template>
  <div class="trend">
    <div class="legend">
      <span v-for="item in legend" :key="item.label" class="legend-item">
        <i class="legend-mark" :style="{ background: item.color, height: item.line ? '2px' : '8px' }" />
        {{ item.label }}
      </span>
    </div>
    <svg :viewBox="`0 0 ${W} ${H}`" class="trend-svg" role="img" aria-label="审查趋势图">
      <defs>
        <linearGradient id="qz-bar" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#7c5cf5" />
          <stop offset="1" stop-color="#c9bcfb" />
        </linearGradient>
      </defs>

      <g v-for="tick in ticks" :key="tick.value">
        <line :x1="PAD.l" :y1="tick.y" :x2="W - PAD.r" :y2="tick.y" stroke="#f0f1f7" stroke-width="1" />
        <text :x="PAD.l - 10" :y="tick.y + 4" text-anchor="end" class="axis-text">{{ tick.value }}</text>
      </g>

      <g v-for="(point, index) in plotted" :key="index">
        <rect
          :x="point.barX"
          :y="point.barY"
          :width="BAR_W"
          :height="point.barH"
          rx="4"
          fill="url(#qz-bar)"
        >
          <title>{{ point.label }}：{{ point.bars }} 份</title>
        </rect>
        <text :x="point.centerX" :y="H - 12" text-anchor="middle" class="axis-text">{{ point.label }}</text>
      </g>

      <path :d="linePath" fill="none" stroke="#f0776f" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      <g v-for="(point, index) in plotted" :key="`dot-${index}`">
        <circle :cx="point.centerX" :cy="point.lineY" r="3.2" fill="#ffffff" stroke="#f0776f" stroke-width="2" />
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface TrendPoint {
  label: string
  bars: number
  line: number
}

const props = withDefaults(
  defineProps<{
    data: TrendPoint[]
    barLabel?: string
    lineLabel?: string
  }>(),
  { barLabel: '审查合同', lineLabel: '中高风险' }
)

const W = 680
const H = 250
const PAD = { l: 38, r: 16, t: 18, b: 34 }
const BAR_W = 16

const legend = computed(() => [
  { label: props.barLabel, color: '#7c5cf5', line: false },
  { label: props.lineLabel, color: '#f0776f', line: true },
])

const niceMax = computed(() => {
  const peak = Math.max(10, ...props.data.map((d) => Math.max(d.bars, d.line)))
  return Math.max(15, Math.ceil(peak / 15) * 15)
})

const plotH = computed(() => H - PAD.t - PAD.b)
const step = computed(() => (W - PAD.l - PAD.r) / Math.max(props.data.length, 1))

const ticks = computed(() =>
  Array.from({ length: 4 }).map((_, i) => {
    const value = Math.round((niceMax.value / 3) * (3 - i))
    return { value, y: PAD.t + (plotH.value / 3) * i }
  })
)

const plotted = computed(() =>
  props.data.map((point, index) => {
    const centerX = PAD.l + step.value * index + step.value / 2
    const barH = Math.max(2, (point.bars / niceMax.value) * plotH.value)
    const lineY = PAD.t + plotH.value - (point.line / niceMax.value) * plotH.value
    return {
      ...point,
      centerX,
      barX: centerX - BAR_W / 2,
      barY: PAD.t + plotH.value - barH,
      barH,
      lineY,
    }
  })
)

const linePath = computed(() =>
  plotted.value.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.centerX},${point.lineY}`).join(' ')
)
</script>

<style scoped>
.trend {
  position: relative;
}
.legend {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-content: flex-end;
  padding-right: 6px;
  margin-bottom: -4px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--qz-ink-3);
}
.legend-mark {
  width: 12px;
  border-radius: 3px;
  display: inline-block;
}
.trend-svg {
  width: 100%;
  height: auto;
  display: block;
  overflow: visible;
}
.axis-text {
  font-size: 10px;
  fill: #a2a8bb;
  font-family: var(--qz-font, Inter, "PingFang SC", sans-serif);
}
</style>
