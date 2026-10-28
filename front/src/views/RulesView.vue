<template>
  <div class="qz-page">
    <PageHeader title="规则中心" description="将法务经验沉淀为可配置、可追溯的合同审查标准。">
      <template #actions>
        <el-button @click="testVisible = true">
          <el-icon><Aim /></el-icon>
          规则测试
        </el-button>
        <el-button type="primary" @click="createSet">
          <el-icon><Plus /></el-icon>
          新建规则集
        </el-button>
      </template>
    </PageHeader>

    <div class="rules-layout">
      <aside class="qz-panel sets-panel">
        <div class="sets-head">
          <div class="qz-panel-title">规则集</div>
          <div class="qz-panel-sub">按合同类型管理审查规则</div>
        </div>
        <div class="sets-search">
          <el-input v-model="setKeyword" placeholder="搜索规则集" :prefix-icon="Search" clearable />
        </div>
        <button
          v-for="set in filteredSets"
          :key="set.id"
          class="set-item"
          :class="{ active: currentSetId === set.id }"
          @click="currentSetId = set.id"
        >
          <div class="set-icon"><el-icon><Files /></el-icon></div>
          <div class="set-meta">
            <div class="set-name">
              {{ set.name }}
              <span class="set-version">{{ set.version }}</span>
            </div>
            <div class="set-sub">{{ set.contractType }} · {{ set.ruleCount }} 条规则</div>
            <div class="set-date">更新于 {{ set.updatedAt }}</div>
          </div>
          <span class="qz-chip" :class="set.status === '已发布' ? 'qz-chip--success' : 'qz-chip--warn'">
            {{ set.status }}
          </span>
        </button>
      </aside>

      <section class="qz-panel rule-detail" v-if="currentSet">
        <div class="detail-head">
          <div class="detail-copy">
            <div class="detail-title">
              {{ currentSet.name }}
              <span class="version-chip">{{ currentSet.version }}</span>
              <span class="qz-chip" :class="currentSet.status === '已发布' ? 'qz-chip--success' : 'qz-chip--warn'">
                {{ currentSet.status }}
              </span>
            </div>
            <p class="detail-sub">{{ currentSet.summary }}</p>
          </div>
          <div class="detail-actions">
            <el-button @click="ElMessage.success('已复制为草稿版本，可独立编辑')">
              <el-icon><CopyDocument /></el-icon>
              复制版本
            </el-button>
            <el-button type="primary" @click="ruleDialog = true">
              <el-icon><Plus /></el-icon>
              添加规则
            </el-button>
          </div>
        </div>

        <div class="stat-strip">
          <div class="strip-item">
            <span>规则总数</span>
            <strong>{{ currentSet.ruleCount }}</strong>
          </div>
          <div class="strip-item">
            <span>高风险规则</span>
            <strong class="danger">{{ highRuleCount }}</strong>
          </div>
          <div class="strip-item">
            <span>已启用规则</span>
            <strong>{{ enabledCount }}</strong>
          </div>
          <div class="strip-item">
            <span>本月命中</span>
            <strong>286</strong>
          </div>
        </div>

        <div class="rule-filters">
          <el-input
            v-model="ruleKeyword"
            class="rule-search"
            placeholder="搜索规则"
            :prefix-icon="Search"
            clearable
          />
          <el-select v-model="categoryFilter" class="rule-select" placeholder="全部分类" clearable>
            <el-option v-for="category in ruleCategories" :key="category" :label="category" :value="category" />
          </el-select>
          <el-select v-model="levelFilter" class="rule-select" placeholder="全部风险" clearable>
            <el-option label="高风险" value="high" />
            <el-option label="中风险" value="medium" />
            <el-option label="低风险" value="low" />
          </el-select>
        </div>

        <div class="rule-list">
          <div v-for="(rule, index) in filteredRules" :key="rule.id" class="rule-row">
            <span class="rule-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <div class="rule-main">
              <div class="rule-title">{{ rule.title }}</div>
              <div class="rule-desc">{{ rule.desc }}</div>
              <div class="rule-tags">
                <span class="qz-chip qz-chip--muted">{{ rule.category }}</span>
                <span class="qz-chip" :class="`qz-chip--${levelMeta(rule.level).tone}`">
                  {{ levelMeta(rule.level).text }}
                </span>
              </div>
            </div>
            <div class="rule-tools">
              <el-switch v-model="rule.enabled" @change="onToggle(rule)" />
              <el-dropdown trigger="click" @command="(command: string) => onRuleCommand(command, rule)">
                <button class="more-btn"><el-icon><MoreFilled /></el-icon></button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="edit">编辑规则</el-dropdown-item>
                    <el-dropdown-item command="copy">复制规则</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除规则</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
          <el-empty v-if="!filteredRules.length" description="没有匹配的规则" :image-size="72" />
        </div>
      </section>
    </div>

    <el-dialog v-model="ruleDialog" title="添加审查规则" width="520px">
      <el-form label-position="top">
        <el-form-item label="规则名称">
          <el-input v-model="newRule.title" placeholder="如：付款节点与交付里程碑绑定" maxlength="40" />
        </el-form-item>
        <el-form-item label="规则说明">
          <el-input v-model="newRule.desc" type="textarea" :rows="3" placeholder="描述触发条件与提示口径" maxlength="120" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="规则分类">
            <el-select v-model="newRule.category" style="width: 100%">
              <el-option v-for="category in ruleCategories" :key="category" :label="category" :value="category" />
            </el-select>
          </el-form-item>
          <el-form-item label="风险等级">
            <el-select v-model="newRule.level" style="width: 100%">
              <el-option label="高风险" value="high" />
              <el-option label="中风险" value="medium" />
              <el-option label="低风险" value="low" />
            </el-select>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialog = false">取消</el-button>
        <el-button type="primary" @click="addRule">保存并启用</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testVisible" title="规则测试沙箱" width="560px">
      <p class="test-tip">粘贴一段合同条款，立即验证当前规则集能否命中。</p>
      <el-input v-model="testText" type="textarea" :rows="5" placeholder="例如：甲方应在合同签订后五个工作日内支付 40% 预付款…" />
      <div v-if="testHits.length" class="test-result">
        <div class="test-result-head">命中 {{ testHits.length }} 条规则</div>
        <div v-for="rule in testHits" :key="rule.id" class="test-hit">
          <span class="qz-chip" :class="`qz-chip--${levelMeta(rule.level).tone}`">{{ levelMeta(rule.level).text }}</span>
          <span class="test-hit-title">{{ rule.title }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="testVisible = false">关闭</el-button>
        <el-button type="primary" @click="runTest">运行测试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Aim, CopyDocument, Files, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { DEMO_RULE_SETS, type DemoRule } from '@/mock/demo'
import { levelMeta } from '@/utils/contractDisplay'

const ruleSets = ref(DEMO_RULE_SETS.map((set) => ({ ...set, rules: set.rules.map((rule) => ({ ...rule })) })))

const currentSetId = ref(ruleSets.value[0].id)
const setKeyword = ref('')
const ruleKeyword = ref('')
const categoryFilter = ref('')
const levelFilter = ref('')

const ruleDialog = ref(false)
const testVisible = ref(false)
const testText = ref('')
const testHits = ref<DemoRule[]>([])

const newRule = reactive({
  title: '',
  desc: '',
  category: '付款条款',
  level: 'high' as 'high' | 'medium' | 'low',
})

const filteredSets = computed(() => {
  const query = setKeyword.value.trim()
  if (!query) return ruleSets.value
  return ruleSets.value.filter((set) => set.name.includes(query) || set.contractType.includes(query))
})

const currentSet = computed(() => ruleSets.value.find((set) => set.id === currentSetId.value) ?? ruleSets.value[0])

const ruleCategories = computed(() => Array.from(new Set(currentSet.value.rules.map((rule) => rule.category))))

const filteredRules = computed(() =>
  currentSet.value.rules.filter((rule) => {
    if (ruleKeyword.value && !`${rule.title}${rule.desc}`.includes(ruleKeyword.value.trim())) return false
    if (categoryFilter.value && rule.category !== categoryFilter.value) return false
    if (levelFilter.value && rule.level !== levelFilter.value) return false
    return true
  })
)

const highRuleCount = computed(() => currentSet.value.rules.filter((rule) => rule.level === 'high').length)
const enabledCount = computed(() => currentSet.value.rules.filter((rule) => rule.enabled).length)

const onToggle = (rule: DemoRule) => {
  ElMessage.success(`「${rule.title}」已${rule.enabled ? '启用' : '停用'}`)
}

const onRuleCommand = (command: string, rule: DemoRule) => {
  if (command === 'delete') {
    const set = currentSet.value
    set.rules = set.rules.filter((item) => item.id !== rule.id)
    ElMessage.success('规则已删除')
    return
  }
  ElMessage.success(command === 'edit' ? '规则编辑面板已打开' : '规则已复制为草稿')
}

const createSet = () => {
  const id = `rs-${Date.now()}`
  ruleSets.value.push({
    id,
    name: '新规则集',
    version: 'V1.0',
    contractType: '服务合同',
    ruleCount: 0,
    status: '草稿',
    updatedAt: new Date().toISOString().slice(0, 10),
    summary: '尚未配置审查规则，请添加第一条规则。',
    rules: [],
  })
  currentSetId.value = id
  ElMessage.success('已创建草稿规则集')
}

const addRule = () => {
  if (!newRule.title.trim()) {
    ElMessage.warning('请填写规则名称')
    return
  }
  const set = currentSet.value
  set.rules.unshift({
    id: `r-${Date.now()}`,
    title: newRule.title.trim(),
    desc: newRule.desc.trim() || '待补充规则说明',
    category: newRule.category,
    level: newRule.level,
    enabled: true,
  })
  set.ruleCount = set.rules.length
  ruleDialog.value = false
  newRule.title = ''
  newRule.desc = ''
  ElMessage.success('规则已保存并启用')
}

const runTest = () => {
  if (!testText.value.trim()) {
    ElMessage.warning('请先粘贴一段合同条款')
    return
  }
  const text = testText.value
  testHits.value = currentSet.value.rules.filter(
    (rule) => rule.enabled && (text.includes(rule.title.slice(0, 2)) || text.includes(rule.category))
  )
  if (!testHits.value.length) {
    ElMessage.info('未命中规则，可尝试补充付款、验收、违约责任等条款描述')
  }
}
</script>

<style scoped>
.rules-layout {
  display: grid;
  grid-template-columns: 296px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.sets-panel {
  padding: 16px 10px;
  position: sticky;
  top: 0;
}
.sets-head {
  padding: 2px 8px 12px;
}
.sets-search {
  padding: 0 8px 12px;
}
.set-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 11px 10px;
  margin-bottom: 4px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
}
.set-item:hover {
  background: #fafaff;
}
.set-item.active {
  background: #f7f4ff;
  border-color: var(--qz-primary-line);
}
.set-icon {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--qz-primary-soft);
  color: var(--qz-primary);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 14px;
}
.set-meta {
  flex: 1;
  min-width: 0;
}
.set-name {
  font-size: 12.8px;
  font-weight: 600;
  color: var(--qz-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.set-version {
  margin-left: 4px;
  font-size: 10px;
  color: var(--qz-primary);
  font-weight: 600;
}
.set-sub {
  margin-top: 3px;
  font-size: 11px;
  color: var(--qz-ink-3);
}
.set-date {
  margin-top: 3px;
  font-size: 10.5px;
  color: var(--qz-muted);
}
.set-item .qz-chip {
  height: 20px;
  font-size: 10.5px;
  padding: 0 6px;
  flex-shrink: 0;
}

.rule-detail {
  padding: 20px 22px 8px;
}
.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.detail-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 17px;
  font-weight: 700;
  color: var(--qz-ink);
}
.version-chip {
  padding: 2px 7px;
  border-radius: 6px;
  background: #f3f4f9;
  color: var(--qz-ink-3);
  font-size: 10.5px;
  font-weight: 600;
}
.detail-sub {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--qz-ink-3);
}
.detail-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin: 18px 0 4px;
  padding: 14px 8px;
  background: #fafbfe;
  border-radius: 11px;
}
.strip-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-left: 14px;
  border-left: 1px solid var(--qz-line);
}
.strip-item:first-child {
  border-left: 0;
}
.strip-item span {
  font-size: 11.5px;
  color: var(--qz-muted);
}
.strip-item strong {
  font-size: 21px;
  font-weight: 700;
  color: var(--qz-ink);
  line-height: 1;
}
.strip-item strong.danger {
  color: #d93a3f;
}
.rule-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 0 6px;
}
.rule-search {
  width: 250px;
}
.rule-select {
  width: 130px;
}
.rule-list {
  margin-top: 4px;
}
.rule-row {
  display: flex;
  gap: 12px;
  padding: 15px 6px;
  border-top: 1px solid var(--qz-line);
  align-items: flex-start;
}
.rule-index {
  width: 22px;
  font-size: 11px;
  color: #b7bccd;
  padding-top: 2px;
  flex-shrink: 0;
  font-family: "SFMono-Regular", Consolas, monospace;
}
.rule-main {
  flex: 1;
  min-width: 0;
}
.rule-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink);
}
.rule-desc {
  margin-top: 5px;
  font-size: 12px;
  color: var(--qz-ink-3);
  line-height: 1.55;
}
.rule-tags {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.rule-tools {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.more-btn {
  width: 24px;
  height: 24px;
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
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.test-tip {
  margin: 0 0 10px;
  font-size: 12.5px;
  color: var(--qz-ink-3);
}
.test-result {
  margin-top: 14px;
  padding: 12px;
  background: #fafbfe;
  border-radius: 10px;
}
.test-result-head {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--qz-ink);
  margin-bottom: 8px;
}
.test-hit {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 12.5px;
  color: var(--qz-ink-2);
}

@media (max-width: 1200px) {
  .rules-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .sets-panel {
    position: static;
  }
}
</style>
