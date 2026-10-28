<template>
  <div class="doc-viewer">
    <div class="doc-toolbar">
      <div class="doc-tools-left">
        <el-icon><Search /></el-icon>
        <span class="doc-file">{{ fileName || title }}</span>
      </div>
      <div class="doc-tools-right">
        <button class="tool-btn" title="缩小" @click="zoomBy(-0.1)"><el-icon><ZoomOut /></el-icon></button>
        <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
        <button class="tool-btn" title="放大" @click="zoomBy(0.1)"><el-icon><ZoomIn /></el-icon></button>
        <span class="tool-divider" />
        <button class="tool-btn" title="旋转" @click="rotate"><el-icon><RefreshRight /></el-icon></button>
        <button class="tool-btn" title="全屏查看" @click="fullscreen = true"><el-icon><FullScreen /></el-icon></button>
      </div>
    </div>

    <div class="doc-body">
      <aside class="thumbs">
        <button
          v-for="(page, index) in pages"
          :key="index"
          class="thumb"
          :class="{ active: index === current }"
          @click="current = index"
        >
          <AppImage :src="page" ratio="720 / 1018" fit="cover" radius="5px" :lazy="false" :previewable="false" />
          <span class="thumb-no">{{ index + 1 }}</span>
        </button>
      </aside>

      <div class="stage">
        <div class="page-frame" :style="{ width: `${PAGE_W * zoom}px`, transform: `rotate(${rotation}deg)` }">
          <AppImage
            :src="pages[current]"
            :alt="`${title} 第 ${current + 1} 页`"
            fit="contain"
            radius="6px"
            :lazy="false"
            previewable
            fallback-text="合同页面加载失败"
          />
        </div>
      </div>
    </div>

    <div class="doc-footer">
      <span>第 {{ current + 1 }} / {{ pages.length }} 页</span>
      <div class="pager">
        <button class="tool-btn" :disabled="current === 0" @click="current -= 1">
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <button class="tool-btn" :disabled="current >= pages.length - 1" @click="current += 1">
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
    </div>

    <el-dialog v-model="fullscreen" fullscreen append-to-body class="doc-fullscreen" :title="title">
      <div class="fullscreen-stage">
        <AppImage :src="pages[current]" fit="contain" :lazy="false" :previewable="true" radius="6px" />
      </div>
      <template #footer>
        <div class="fullscreen-footer">
          <el-button :disabled="current === 0" @click="current -= 1">上一页</el-button>
          <span class="qz-muted">{{ current + 1 }} / {{ pages.length }}</span>
          <el-button :disabled="current >= pages.length - 1" @click="current += 1">下一页</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  FullScreen,
  RefreshRight,
  Search,
  ZoomIn,
  ZoomOut,
} from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import { contractPageImage, wrapText } from '@/utils/placeholder'

const props = withDefaults(
  defineProps<{
    title: string
    fileName?: string
    text: string
    highlights?: string[]
    pageLineCount?: number
  }>(),
  { fileName: '', highlights: () => [], pageLineCount: 26 }
)

const PAGE_W = 500
const current = ref(0)
const zoom = ref(1)
const rotation = ref(0)
const fullscreen = ref(false)

const lines = computed(() => {
  const list = wrapText(props.text || '暂无合同正文内容', 28)
  // 正文首行通常就是合同标题，页面已单独排版，避免重复
  const head = (list[0] ?? '').replace(/\s/g, '')
  if (head && (head === props.title.replace(/\s/g, '') || head === props.title.replace(/\s/g, '').concat('.docx'))) {
    return list.slice(1)
  }
  return list
})

const pages = computed(() => {
  const chunks: string[][] = []
  for (let i = 0; i < lines.value.length; i += props.pageLineCount) {
    chunks.push(lines.value.slice(i, i + props.pageLineCount))
  }
  if (!chunks.length) chunks.push([''])
  return chunks.map((chunk, index) =>
    contractPageImage({
      title: props.title,
      lines: chunk,
      page: index + 1,
      total: chunks.length,
      highlights: props.highlights,
      stamped: index === chunks.length - 1,
    })
  )
})

const zoomBy = (delta: number) => {
  zoom.value = Math.min(1.8, Math.max(0.6, Math.round((zoom.value + delta) * 10) / 10))
}

const rotate = () => {
  rotation.value = (rotation.value + 90) % 360
}

watch(
  () => props.text,
  () => {
    current.value = 0
    zoom.value = 1
    rotation.value = 0
  }
)

watch(pages, (list) => {
  if (current.value > list.length - 1) current.value = Math.max(0, list.length - 1)
})

/** 供父组件按条款原文定位页码（AI 初审「定位原文」） */
const locate = (keyword: string) => {
  const needle = (keyword || '').replace(/\s+/g, '').slice(0, 12)
  if (!needle) return false
  const index = lines.value.findIndex((line) => line.replace(/\s+/g, '').includes(needle))
  if (index < 0) return false
  current.value = Math.floor(index / props.pageLineCount)
  return true
}

defineExpose({ locate })
</script>

<style scoped>
.doc-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #f7f8fc;
  border-radius: var(--qz-radius);
  border: 1px solid var(--qz-line);
  overflow: hidden;
}
.doc-toolbar {
  height: 46px;
  flex-shrink: 0;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #ffffff;
  border-bottom: 1px solid var(--qz-line);
}
.doc-tools-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--qz-muted);
}
.doc-file {
  font-size: 12.5px;
  color: var(--qz-ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-tools-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.tool-btn {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--qz-ink-3);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}
.tool-btn:hover:not(:disabled) {
  background: var(--qz-primary-soft);
  color: var(--qz-primary);
}
.tool-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.zoom-value {
  min-width: 42px;
  text-align: center;
  font-size: 12px;
  color: var(--qz-ink-2);
}
.tool-divider {
  width: 1px;
  height: 16px;
  background: var(--qz-line-strong);
  margin: 0 4px;
}
.doc-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}
.thumbs {
  width: 86px;
  flex-shrink: 0;
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  background: #ffffff;
  border-right: 1px solid var(--qz-line);
}
.thumb {
  position: relative;
  padding: 3px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease;
}
.thumb:hover {
  background: #f7f5ff;
}
.thumb.active {
  border-color: var(--qz-primary);
  background: var(--qz-primary-soft);
}
.thumb-no {
  display: block;
  margin-top: 4px;
  font-size: 10px;
  color: var(--qz-muted);
  text-align: center;
}
.thumb.active .thumb-no {
  color: var(--qz-primary);
  font-weight: 600;
}
.stage {
  flex: 1 1 auto;
  min-width: 0;
  padding: 20px;
  overflow: auto;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  background: #f2f3f9;
}
.page-frame {
  transition: width 0.18s ease, transform 0.25s ease;
  box-shadow: 0 14px 34px rgba(28, 26, 60, 0.14);
  border-radius: 6px;
  background: #ffffff;
  flex-shrink: 0;
}
.doc-footer {
  height: 40px;
  flex-shrink: 0;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-top: 1px solid var(--qz-line);
  font-size: 12px;
  color: var(--qz-muted);
}
.pager {
  display: flex;
  gap: 4px;
}
.fullscreen-stage {
  height: 100%;
  display: grid;
  place-items: center;
  background: #f2f3f9;
  border-radius: 10px;
  padding: 16px;
}
.fullscreen-stage :deep(.app-image) {
  height: calc(100vh - 180px);
  max-width: 900px;
}
.fullscreen-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
</style>
