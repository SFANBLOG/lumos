<template>
  <header class="qz-page-head">
    <div class="head-copy">
      <div v-if="eyebrow" class="head-eyebrow">{{ eyebrow }}</div>
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
      <slot />
    </div>
    <div class="qz-head-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ title: string; description?: string; eyebrow?: string }>(), {
  description: '',
  eyebrow: '',
})
</script>

<style scoped>
.head-copy {
  min-width: 0;
}
.head-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.4px;
  color: var(--qz-primary);
  text-transform: uppercase;
}
</style>
