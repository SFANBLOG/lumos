<template>
  <div class="app-image" :style="boxStyle">
    <el-image
      v-if="src"
      class="app-image__inner"
      :src="src"
      :alt="alt"
      :fit="fit"
      :lazy="lazy"
      :preview-src-list="previewable ? [src] : []"
      preview-teleported
      hide-on-click-modal
      :initial-index="0"
    >
      <template #placeholder>
        <div class="app-image__ph">
          <span class="app-image__shimmer" />
        </div>
      </template>
      <template #error>
        <div class="app-image__ph app-image__ph--error">
          <el-icon><Picture /></el-icon>
          <span>{{ fallbackText }}</span>
        </div>
      </template>
    </el-image>
    <div v-else class="app-image__ph app-image__ph--error">
      <el-icon><Picture /></el-icon>
      <span>{{ fallbackText }}</span>
    </div>

    <span v-if="caption" class="app-image__caption">{{ caption }}</span>
    <span v-if="previewable && src" class="app-image__zoom">
      <el-icon><ZoomIn /></el-icon>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Picture, ZoomIn } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    src?: string
    alt?: string
    width?: string
    height?: string
    ratio?: string
    fit?: 'fill' | 'contain' | 'cover' | 'none' | 'scale-down'
    radius?: string
    previewable?: boolean
    lazy?: boolean
    caption?: string
    fallbackText?: string
  }>(),
  {
    src: '',
    alt: '图片',
    width: '100%',
    height: '',
    ratio: '',
    fit: 'cover',
    radius: '12px',
    previewable: false,
    lazy: true,
    caption: '',
    fallbackText: '图片暂不可用',
  }
)

const boxStyle = computed(() => ({
  width: props.width,
  height: props.height || undefined,
  aspectRatio: props.height ? undefined : props.ratio || undefined,
  borderRadius: props.radius,
}))
</script>

<style scoped>
.app-image {
  position: relative;
  overflow: hidden;
  background: #f5f6fb;
  display: block;
}
.app-image__inner {
  width: 100%;
  height: 100%;
  display: block;
}
.app-image__ph {
  width: 100%;
  height: 100%;
  min-height: 72px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #a8aec0;
  font-size: 12px;
  background: #f5f6fb;
  overflow: hidden;
}
.app-image__ph--error {
  background: linear-gradient(135deg, #f7f5ff, #f2f4fb);
}
.app-image__ph--error .el-icon {
  font-size: 20px;
  color: #c3c7d8;
}
.app-image__shimmer {
  width: 42%;
  height: 8px;
  border-radius: 8px;
  background: linear-gradient(90deg, #eef0f7 25%, #e3e6f1 37%, #eef0f7 63%);
  background-size: 400% 100%;
  animation: qz-shimmer 1.4s ease infinite;
}
@keyframes qz-shimmer {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}
.app-image__caption {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 18px 12px 8px;
  font-size: 12px;
  color: #ffffff;
  background: linear-gradient(180deg, rgba(16, 14, 38, 0), rgba(16, 14, 38, 0.72));
}
.app-image__zoom {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  background: rgba(20, 18, 40, 0.45);
  color: #ffffff;
  font-size: 13px;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.app-image:hover .app-image__zoom {
  opacity: 1;
}
</style>
