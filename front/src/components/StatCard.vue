<template>
  <div class="qz-stat">
    <div class="stat-main">
      <div class="qz-icon-box stat-icon" :class="`qz-icon-box--${tone}`">
        <slot name="icon" />
      </div>
      <div class="stat-meta">
        <div class="stat-label">{{ label }}</div>
        <div class="stat-value">
          {{ value }}<span v-if="unit" class="stat-unit">{{ unit }}</span>
        </div>
      </div>
    </div>
    <div v-if="$slots.foot" class="stat-foot">
      <slot name="foot" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string | number
    unit?: string
    tone?: 'primary' | 'warn' | 'info' | 'success' | 'danger'
  }>(),
  { unit: '', tone: 'primary' }
)
</script>

<style scoped>
.qz-stat {
  background: var(--qz-card);
  border: 1px solid var(--qz-line);
  border-radius: var(--qz-radius);
  padding: 18px 20px 16px;
  box-shadow: var(--qz-shadow);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  height: 100%;
}
.qz-stat:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 26px rgba(28, 26, 60, 0.07);
}
.stat-main {
  display: flex;
  align-items: center;
  gap: 14px;
}
.stat-icon {
  width: 46px;
  height: 46px;
  font-size: 21px;
}
.stat-meta {
  min-width: 0;
}
.stat-label {
  font-size: 12.5px;
  color: var(--qz-ink-3);
  margin-bottom: 5px;
}
.stat-value {
  font-size: 27px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.5px;
  color: var(--qz-ink);
}
.stat-unit {
  margin-left: 4px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--qz-muted);
  letter-spacing: 0;
}
.stat-foot {
  margin-top: 12px;
  font-size: 12px;
  color: var(--qz-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
