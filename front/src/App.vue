<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
:root {
  --ink-950: #0b1f33;
  --ink-900: #102a43;
  --ink-800: #193b59;
  --ink-600: #486581;
  --canvas: #f5f7fa;
  --paper: #ffffff;
  --line: #e2e8f0;
  --brand: #1d4ed8;
  --brand-soft: #eaf1ff;
  --accent: #b7791f;
  --danger: #c2413b;
  --el-color-primary: #1d4ed8;
  --el-color-primary-light-3: #5b82e8;
  --el-color-primary-light-5: #91adef;
  --el-color-primary-light-9: #eef4ff;
  --el-color-success: #2f855a;
  --el-color-warning: #b7791f;
  --el-color-danger: #c2413b;
  --el-border-color: #e2e8f0;
  --el-border-color-light: #edf1f5;
  --el-border-radius-base: 8px;
  color: var(--ink-900);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--canvas); }
.el-card { border-color: var(--line); border-radius: 12px; }
.el-card__header { border-bottom-color: var(--line); }
.el-button--primary { font-weight: 600; }
</style>
