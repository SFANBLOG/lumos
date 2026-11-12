<template>
  <div v-if="isDemoMode" class="demo-mode-banner">
    演示数据模式 · 当前展示的是示例内容，不代表真实业务结果
  </div>
  <router-view />
</template>

<script setup lang="ts">
import { isDemoMode } from '@/utils/demoMode'
</script>

<style scoped>
.demo-mode-banner {
  position: sticky;
  top: 0;
  z-index: 2000;
  padding: 6px 16px;
  background: #fdf6ec;
  border-bottom: 1px solid #f5dab1;
  color: #a15c00;
  font-size: 12px;
  text-align: center;
}
</style>
