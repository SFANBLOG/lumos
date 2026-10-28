<template>
  <div class="qz-page">
    <PageHeader title="知识库" description="统一管理 AI 审查所依据的法规、制度、模板与案例。">
      <template #actions>
        <el-button :loading="syncing" @click="syncSources">
          <el-icon><Refresh /></el-icon>
          同步法规
        </el-button>
        <el-button type="primary" @click="uploadVisible = true">
          <el-icon><Upload /></el-icon>
          上传资料
        </el-button>
      </template>
    </PageHeader>

    <div class="category-grid">
      <button
        v-for="category in categories"
        :key="category.key"
        class="category-card"
        :class="{ active: activeTab === category.key }"
        @click="selectCategory(category.key)"
      >
        <div class="qz-icon-box" :class="`qz-icon-box--${category.tone}`">
          <el-icon><component :is="category.icon" /></el-icon>
        </div>
        <div class="category-meta">
          <div class="category-title">{{ category.title }}</div>
          <div class="category-desc">{{ category.desc }}</div>
          <div class="category-count">{{ category.count }} 份资料</div>
        </div>
        <el-icon class="category-arrow"><ArrowRight /></el-icon>
      </button>
    </div>

    <section class="qz-panel">
      <div class="status-tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          class="status-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="filters">
        <el-input
          v-model="keyword"
          class="filter-search"
          placeholder="搜索资料名称或内容"
          :prefix-icon="Search"
          clearable
        />
        <el-select v-model="typeFilter" class="filter-select" placeholder="适用合同类型" clearable>
          <el-option label="采购合同" value="采购合同" />
          <el-option label="销售合同" value="销售合同" />
          <el-option label="技术合同" value="技术合同" />
          <el-option label="劳动合同" value="劳动合同" />
        </el-select>
        <el-select v-model="statusFilter" class="filter-select" placeholder="状态" clearable>
          <el-option label="已生效" value="已生效" />
          <el-option label="已发布" value="已发布" />
          <el-option label="草稿" value="草稿" />
        </el-select>
        <span class="filter-total">共 {{ filteredItems.length }} 份资料</span>
      </div>

      <el-table :data="filteredItems" class="qz-table" empty-text="没有匹配的资料">
        <el-table-column label="资料名称" min-width="320">
          <template #default="{ row }">
            <div class="doc-cell">
              <AppImage
                :src="knowledgeCover(row.cover, row.category)"
                width="36px"
                height="46px"
                radius="7px"
                fit="cover"
                previewable
                :lazy="false"
                :alt="row.name"
              />
              <div class="doc-meta">
                <div class="doc-name">{{ row.name }}</div>
                <div class="doc-code">更新于 {{ row.updatedAt }} · 管理员</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="120">
          <template #default="{ row }">
            <span class="qz-chip" :class="categoryTone(row.categoryKey)">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="版本/生效日期" width="148">
          <template #default="{ row }">
            <span class="mono-text">{{ row.version }}</span>
          </template>
        </el-table-column>
        <el-table-column label="向量化状态" width="150">
          <template #default="{ row }">
            <span class="vector-cell">
              <i class="vector-dot" />
              {{ row.chunks.toLocaleString() }} 个切片
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="112">
          <template #default="{ row }">
            <span class="status-cell">
              <i class="status-dot" :class="{ draft: row.status === '草稿' }" />
              {{ row.status }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button link type="primary" @click="preview(row)">查看</el-button>
              <el-dropdown trigger="click" @command="(command: string) => onCommand(command, row)">
                <button class="more-btn"><el-icon><MoreFilled /></el-icon></button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="reindex">重新向量化</el-dropdown-item>
                    <el-dropdown-item command="download">下载原文</el-dropdown-item>
                    <el-dropdown-item command="offline" divided>下线资料</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="previewVisible" :title="previewItem?.name ?? '资料预览'" width="760px" top="6vh">
      <div v-if="previewItem" class="preview-dialog">
        <AppImage
          :src="knowledgeCover(previewItem.cover, previewItem.category)"
          width="220px"
          height="282px"
          radius="12px"
          fit="cover"
          previewable
          :lazy="false"
        />
        <div class="preview-meta">
          <span class="qz-chip" :class="categoryTone(previewItem.categoryKey)">{{ previewItem.category }}</span>
          <h3>{{ previewItem.name }}</h3>
          <p>更新于 {{ previewItem.updatedAt }} · 版本 {{ previewItem.version }}</p>
          <div class="preview-stats">
            <div>
              <span>向量切片</span>
              <strong>{{ previewItem.chunks.toLocaleString() }}</strong>
            </div>
            <div>
              <span>生效状态</span>
              <strong>{{ previewItem.status }}</strong>
            </div>
            <div>
              <span>引用次数</span>
              <strong>{{ (previewItem.chunks % 37) + 12 }}</strong>
            </div>
          </div>
          <p class="preview-desc">
            该资料已进入检索增强生成（RAG）索引，合同审查时按条款语义召回，并在风险项中标注法条出处。
          </p>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="上传资料" width="520px">
      <el-upload drag :auto-upload="false" :show-file-list="false" accept=".pdf,.docx,.txt,.md" :on-change="onPickFile">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">将资料拖到此处，或 <em>点击选择文件</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 PDF / DOCX / TXT / MD，单个文件不超过 20MB</div>
        </template>
      </el-upload>

      <div v-if="pickedFile" class="picked-file">
        <AppImage :src="knowledgeCover('policy', '资料')" width="42px" height="54px" radius="8px" :lazy="false" />
        <div class="picked-meta">
          <div class="picked-name">{{ pickedFile.name }}</div>
          <div class="picked-size">{{ formatSize(pickedFile.size) }}</div>
        </div>
        <el-button link type="danger" @click="pickedFile = null">移除</el-button>
      </div>

      <el-form label-position="top" class="upload-form">
        <el-form-item label="资料分类">
          <el-select v-model="uploadCategory" placeholder="请选择分类" style="width: 100%">
            <el-option label="法律法规" value="法律法规" />
            <el-option label="企业制度" value="企业制度" />
            <el-option label="合同模板" value="合同模板" />
            <el-option label="历史案例" value="历史案例" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!pickedFile" @click="confirmUpload">开始解析并入库</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, ref } from 'vue'
import { ElMessage, type UploadFile } from 'element-plus'
import {
  ArrowRight,
  Collection,
  Document,
  Files,
  MoreFilled,
  OfficeBuilding,
  Refresh,
  Search,
  Upload,
  UploadFilled,
} from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import PageHeader from '@/components/PageHeader.vue'
import { DEMO_KNOWLEDGE_CATEGORIES, DEMO_KNOWLEDGE_ITEMS, type DemoKnowledgeItem } from '@/mock/demo'
import { knowledgeCover } from '@/utils/placeholder'

const TABS = [
  { key: 'all', label: '全部资料' },
  { key: 'law', label: '法律法规' },
  { key: 'policy', label: '企业制度' },
  { key: 'template', label: '合同模板' },
  { key: 'case', label: '历史案例' },
]

const categories = [
  {
    ...DEMO_KNOWLEDGE_CATEGORIES[0],
    icon: markRaw(Document),
    tone: 'primary' as const,
  },
  {
    ...DEMO_KNOWLEDGE_CATEGORIES[1],
    icon: markRaw(OfficeBuilding),
    tone: 'info' as const,
  },
  {
    ...DEMO_KNOWLEDGE_CATEGORIES[2],
    icon: markRaw(Files),
    tone: 'success' as const,
  },
  {
    ...DEMO_KNOWLEDGE_CATEGORIES[3],
    icon: markRaw(Collection),
    tone: 'warn' as const,
  },
]

const activeTab = ref('all')
const keyword = ref('')
const typeFilter = ref('')
const statusFilter = ref('')
const syncing = ref(false)

const previewVisible = ref(false)
const previewItem = ref<DemoKnowledgeItem | null>(null)

const uploadVisible = ref(false)
const uploadCategory = ref('企业制度')
const pickedFile = ref<{ name: string; size: number } | null>(null)

const filteredItems = computed(() =>
  DEMO_KNOWLEDGE_ITEMS.filter((item) => {
    if (activeTab.value !== 'all' && item.categoryKey !== activeTab.value) return false
    if (statusFilter.value && item.status !== statusFilter.value) return false
    if (keyword.value && !item.name.includes(keyword.value.trim())) return false
    return true
  })
)

const categoryTone = (key: string) => {
  switch (key) {
    case 'law':
      return 'qz-chip--primary'
    case 'policy':
      return 'qz-chip--info'
    case 'template':
      return 'qz-chip--success'
    default:
      return 'qz-chip--warn'
  }
}

const selectCategory = (key: string) => {
  activeTab.value = activeTab.value === key ? 'all' : key
}

const preview = (item: DemoKnowledgeItem) => {
  previewItem.value = item
  previewVisible.value = true
}

const syncSources = () => {
  syncing.value = true
  setTimeout(() => {
    syncing.value = false
    ElMessage.success('法规库已同步至最新版本，新增 2 份司法解释')
  }, 900)
}

const onCommand = (command: string, item: DemoKnowledgeItem) => {
  if (command === 'offline') {
    ElMessage.warning(`「${item.name}」已提交下线申请`)
    return
  }
  ElMessage.success(command === 'reindex' ? '已加入重新向量化队列' : '原文下载已开始')
}

const onPickFile = (file: UploadFile) => {
  if (!file.raw) return
  pickedFile.value = { name: file.name, size: file.raw.size }
}

const confirmUpload = () => {
  if (!pickedFile.value) return
  ElMessage.success(`「${pickedFile.value.name}」已提交解析，完成后将自动向量化入库`)
  uploadVisible.value = false
  pickedFile.value = null
}

const formatSize = (size: number) => {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>

<style scoped>
.category-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.category-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 18px;
  border: 1px solid var(--qz-line);
  border-radius: var(--qz-radius);
  background: var(--qz-card);
  box-shadow: var(--qz-shadow);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}
.category-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(28, 26, 60, 0.07);
}
.category-card.active {
  border-color: var(--qz-primary-line);
  background: #fcfbff;
}
.category-meta {
  min-width: 0;
  flex: 1;
}
.category-title {
  font-size: 14px;
  font-weight: 650;
  color: var(--qz-ink);
}
.category-desc {
  margin-top: 5px;
  font-size: 11.5px;
  color: var(--qz-muted);
  line-height: 1.5;
}
.category-count {
  margin-top: 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--qz-ink-2);
}
.category-arrow {
  color: #c3c7d8;
  font-size: 13px;
  margin-top: 2px;
}

.status-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 18px 0;
  border-bottom: 1px solid var(--qz-line);
  overflow-x: auto;
}
.status-tab {
  position: relative;
  padding: 6px 12px 14px;
  border: 0;
  background: transparent;
  color: var(--qz-ink-3);
  font-size: 13.5px;
  cursor: pointer;
  white-space: nowrap;
}
.status-tab.active {
  color: var(--qz-ink);
  font-weight: 600;
}
.status-tab.active::after {
  content: "";
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: -1px;
  height: 2px;
  border-radius: 2px;
  background: var(--qz-primary);
}
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px;
  flex-wrap: wrap;
}
.filter-search {
  width: 300px;
}
.filter-select {
  width: 148px;
}
.filter-total {
  margin-left: auto;
  font-size: 12px;
  color: var(--qz-muted);
}
.doc-cell {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.doc-meta {
  min-width: 0;
}
.doc-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-code {
  margin-top: 4px;
  font-size: 11px;
  color: var(--qz-muted);
}
.mono-text {
  font-size: 12px;
  color: var(--qz-ink-2);
  font-variant-numeric: tabular-nums;
}
.vector-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--qz-ink-2);
}
.vector-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--qz-success);
  box-shadow: 0 0 0 3px rgba(31, 174, 114, 0.12);
}
.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--qz-ink-2);
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--qz-info);
}
.status-dot.draft {
  background: var(--qz-warn);
}
.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}
.more-btn {
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--qz-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.more-btn:hover {
  background: #f2f3f9;
}
.preview-dialog {
  display: flex;
  gap: 22px;
  align-items: flex-start;
}
.preview-meta {
  min-width: 0;
}
.preview-meta h3 {
  margin: 10px 0 6px;
  font-size: 18px;
  color: var(--qz-ink);
}
.preview-meta p {
  margin: 0;
  font-size: 12.5px;
  color: var(--qz-muted);
  line-height: 1.7;
}
.preview-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 18px 0;
  padding: 14px;
  background: #fafbfe;
  border-radius: 10px;
}
.preview-stats div {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.preview-stats span {
  font-size: 11px;
  color: var(--qz-muted);
}
.preview-stats strong {
  font-size: 17px;
  color: var(--qz-ink);
}
.preview-desc {
  padding: 12px;
  background: var(--qz-primary-soft);
  border-radius: 9px;
  color: #5d4da8 !important;
}
.picked-file {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--qz-line);
  border-radius: 10px;
}
.picked-meta {
  flex: 1;
  min-width: 0;
}
.picked-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.picked-size {
  margin-top: 4px;
  font-size: 11px;
  color: var(--qz-muted);
}
.upload-form {
  margin-top: 16px;
}

@media (max-width: 1380px) {
  .category-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .category-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
