<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand" @click="router.push('/dashboard')">
        <div class="brand-mark">契</div>
        <div class="brand-text">
          <div class="brand-name">契智</div>
          <div class="brand-sub">QI ZHI LEGAL INTELLIGENCE</div>
        </div>
      </div>

      <nav class="nav">
        <div v-for="group in MENU" :key="group.title" class="nav-group-wrap">
          <div class="nav-group">{{ group.title }}</div>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isActive(item.path) }"
          >
            <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
            <span class="nav-label">{{ item.title }}</span>
            <span v-if="item.tag" class="nav-tag">{{ item.tag }}</span>
          </router-link>
        </div>
      </nav>

      <div class="secure-card" @click="router.push('/settings')">
        <div class="secure-icon"><el-icon><Lock /></el-icon></div>
        <div class="secure-text">
          <div class="secure-title">数据安全中心</div>
          <div class="secure-sub">本地加密存储 · 全程留痕</div>
        </div>
      </div>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div class="topbar-left">
          <div class="eyebrow">QI ZHI LEGAL INTELLIGENCE</div>
          <div class="topbar-title">{{ pageTitle }}</div>
        </div>

        <div class="topbar-right">
          <div class="search" :class="{ open: searchOpen }">
            <button class="icon-btn" title="搜索" @click="toggleSearch">
              <el-icon><Search /></el-icon>
            </button>
            <input
              v-show="searchOpen"
              ref="searchInput"
              v-model="keyword"
              class="search-input"
              placeholder="搜索合同、条款或编号"
              @keyup.enter="doSearch"
              @keyup.esc="closeSearch"
              @blur="closeSearch"
            />
          </div>

          <el-popover placement="bottom-end" :width="320" trigger="click" popper-class="notice-popper">
            <template #reference>
              <button class="icon-btn notice-btn" title="通知">
                <el-icon><Bell /></el-icon>
                <span class="notice-dot" />
              </button>
            </template>
            <div class="notice-head">
              <span>待办提醒</span>
              <span class="qz-muted">3 条</span>
            </div>
            <button v-for="notice in NOTICES" :key="notice.id" class="notice-row" @click="router.push(notice.to)">
              <span class="notice-mark" :class="`notice-mark--${notice.tone}`" />
              <div>
                <div class="notice-title">{{ notice.title }}</div>
                <div class="notice-sub">{{ notice.desc }}</div>
              </div>
            </button>
            <button class="notice-all" @click="router.push('/contracts')">查看全部待办</button>
          </el-popover>

          <span class="topbar-divider" />

          <el-dropdown trigger="click" @command="onCommand">
            <div class="user">
              <AppImage :src="avatar" :alt="displayName" width="34px" height="34px" radius="10px" :lazy="false" />
              <div class="user-meta">
                <span class="user-name">{{ displayName }}</span>
                <span class="user-role">企业法务</span>
              </div>
              <el-icon class="caret"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人信息</el-dropdown-item>
                <el-dropdown-item command="settings">系统设置</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  Bell,
  Collection,
  DataAnalysis,
  Document,
  Lock,
  Odometer,
  Search,
  Setting,
} from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import { useAuthStore } from '@/stores/auth'
import { avatarImage } from '@/utils/placeholder'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const MENU = [
  {
    title: '法务工作台',
    items: [
      { path: '/dashboard', title: '工作台', icon: markRaw(Odometer) },
      { path: '/contracts', title: '合同管理', icon: markRaw(Document), tag: '3' },
      { path: '/knowledge', title: '知识库', icon: markRaw(Collection) },
    ],
  },
  {
    title: '智能资产',
    items: [
      { path: '/rules', title: '规则中心', icon: markRaw(DataAnalysis) },
      { path: '/reports', title: '审查报告', icon: markRaw(Document) },
      { path: '/settings', title: '系统设置', icon: markRaw(Setting) },
    ],
  },
]

const NOTICES = [
  { id: 1, title: '云服务采购框架协议', desc: '识别 12 项风险，其中高风险 4 项', tone: 'danger', to: '/contracts' },
  { id: 2, title: '品牌年度营销服务合同', desc: 'AI 初审完成，等待人工复核', tone: 'warn', to: '/reports' },
  { id: 3, title: '规则集版本更新', desc: '采购合同审查规则 V3.2 已发布', tone: 'primary', to: '/rules' },
]

const displayName = computed(() => auth.user?.username ?? '林墨')
const avatar = computed(() => avatarImage(displayName.value))

const pageTitle = computed(() => (route.meta?.title as string) || '工作台')

// 详情类页面回挂到所属菜单，避免侧栏无高亮
const detailOwner: Record<string, string> = {
  '/analysis': '/contracts',
  '/review': '/reports',
  '/consult': '/knowledge',
  '/mcp': '/settings',
  '/approvals': '/reports',
  '/playbooks': '/rules',
}
const activePath = computed(() => detailOwner[route.path.split('/').slice(0, 2).join('/')] ?? route.path)
const isActive = (path: string) => activePath.value === path

const searchOpen = ref(false)
const keyword = ref('')
const searchInput = ref<HTMLInputElement | null>(null)

const toggleSearch = async () => {
  searchOpen.value = !searchOpen.value
  if (searchOpen.value) {
    await nextTick()
    searchInput.value?.focus()
  }
}
const closeSearch = () => {
  searchOpen.value = false
}
const doSearch = () => {
  const query = keyword.value.trim()
  if (!query) return
  router.push({ path: '/contracts', query: { q: query } })
  closeSearch()
}

const onCommand = (command: string) => {
  if (command === 'logout') {
    auth.logout()
    router.push('/login')
    return
  }
  router.push(command === 'settings' ? '/settings' : '/settings?tab=profile')
}

onMounted(() => {
  if (auth.isLoggedIn() && !auth.user) {
    auth.fetchUser()
  }
})
</script>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--qz-canvas);
}

/* ── 侧栏 ───────────────────────────────────── */
.sidebar {
  width: 228px;
  flex-shrink: 0;
  background: radial-gradient(120% 60% at 50% 0%, #2a2258 0%, #191633 48%, #15122b 100%);
  padding: 0 12px 14px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255, 255, 255, 0.05);
}
.brand {
  height: 74px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 6px;
  cursor: pointer;
  flex-shrink: 0;
}
.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 11px;
  background: linear-gradient(140deg, #8f78f5, #6c4cf1 55%, #5a3ade);
  color: #ffffff;
  font-size: 17px;
  font-weight: 700;
  display: grid;
  place-items: center;
  box-shadow: 0 6px 16px rgba(108, 76, 241, 0.4);
  flex-shrink: 0;
}
.brand-text {
  min-width: 0;
}
.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 2px;
  line-height: 1.2;
}
.brand-sub {
  font-size: 7.5px;
  letter-spacing: 0.9px;
  color: #8d87b0;
  margin-top: 3px;
  white-space: nowrap;
  transform: scale(0.94);
  transform-origin: left center;
}
.nav {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 6px 0 8px;
  scrollbar-width: none;
}
.nav::-webkit-scrollbar {
  display: none;
}
.nav-group {
  padding: 14px 10px 7px;
  font-size: 10px;
  letter-spacing: 1.3px;
  color: #6d6890;
  font-weight: 600;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 42px;
  padding: 0 12px;
  margin-bottom: 4px;
  border-radius: 10px;
  color: #a8a3c6;
  font-size: 13.5px;
  transition: background 0.18s ease, color 0.18s ease;
}
.nav-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #ffffff;
}
.nav-item.active {
  background: linear-gradient(90deg, #6c4cf1, #5a3ade);
  color: #ffffff;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(90, 58, 222, 0.35);
}
.nav-icon {
  font-size: 17px;
}
.nav-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nav-tag {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.14);
  color: #ffffff;
  font-size: 10.5px;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.nav-item.active .nav-tag {
  background: rgba(255, 255, 255, 0.24);
}
.secure-card {
  margin-top: auto;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: background 0.18s ease;
}
.secure-card:hover {
  background: rgba(255, 255, 255, 0.08);
}
.secure-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: rgba(108, 76, 241, 0.28);
  color: #b7a8fb;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.secure-title {
  font-size: 12px;
  color: #e6e3f5;
  font-weight: 600;
}
.secure-sub {
  margin-top: 3px;
  font-size: 10px;
  color: #7f7a9e;
  white-space: nowrap;
}

/* ── 顶栏 ───────────────────────────────────── */
.workspace {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.topbar {
  height: 64px;
  flex-shrink: 0;
  background: #ffffff;
  border-bottom: 1px solid var(--qz-line);
  padding: 0 24px 0 26px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.topbar-left {
  min-width: 0;
}
.eyebrow {
  font-size: 8.5px;
  letter-spacing: 1.5px;
  color: #b0b4c4;
  font-weight: 600;
  line-height: 1;
  margin-bottom: 5px;
}
.topbar-title {
  font-size: 16px;
  font-weight: 650;
  color: var(--qz-ink);
  letter-spacing: -0.2px;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.icon-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--qz-line);
  border-radius: 10px;
  background: #ffffff;
  color: var(--qz-ink-3);
  display: grid;
  place-items: center;
  cursor: pointer;
  font-size: 15px;
  transition: border-color 0.18s ease, color 0.18s ease, background 0.18s ease;
}
.icon-btn:hover {
  border-color: var(--qz-primary-line);
  color: var(--qz-primary);
  background: var(--qz-primary-soft);
}
.search {
  display: flex;
  align-items: center;
  gap: 6px;
}
.search-input {
  width: 216px;
  height: 34px;
  border: 1px solid var(--qz-line);
  border-radius: 10px;
  padding: 0 12px;
  font-size: 12.5px;
  color: var(--qz-ink);
  outline: none;
  background: #fafbfe;
  transition: border-color 0.18s ease;
}
.search-input:focus {
  border-color: var(--qz-primary);
  background: #ffffff;
}
.notice-btn {
  position: relative;
}
.notice-dot {
  position: absolute;
  top: 7px;
  right: 8px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f04438;
  border: 1.5px solid #ffffff;
}
.topbar-divider {
  width: 1px;
  height: 22px;
  background: var(--qz-line);
  margin: 0 4px;
}
.user {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 4px 8px 4px 4px;
  border-radius: 11px;
  cursor: pointer;
  transition: background 0.18s ease;
}
.user:hover {
  background: #f8f8fc;
}
.user-meta {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--qz-ink);
}
.user-role {
  font-size: 10.5px;
  color: var(--qz-muted);
}
.caret {
  font-size: 12px;
  color: #b0b4c4;
}

/* 通知面板 */
.notice-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--qz-ink);
  padding: 2px 2px 8px;
  border-bottom: 1px solid var(--qz-line);
  margin-bottom: 6px;
}
.notice-row {
  display: flex;
  gap: 9px;
  width: 100%;
  text-align: left;
  padding: 9px 6px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font: inherit;
}
.notice-row:hover {
  background: #f8f8fc;
}
.notice-mark {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}
.notice-mark--danger {
  background: var(--qz-danger);
}
.notice-mark--warn {
  background: var(--qz-warn);
}
.notice-mark--primary {
  background: var(--qz-primary);
}
.notice-title {
  font-size: 12.5px;
  color: var(--qz-ink);
  font-weight: 550;
}
.notice-sub {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--qz-muted);
}
.notice-all {
  width: 100%;
  margin-top: 4px;
  padding-top: 8px;
  border: 0;
  border-top: 1px solid var(--qz-line);
  background: transparent;
  color: var(--qz-primary);
  font-size: 12px;
  cursor: pointer;
}

/* ── 内容区 ─────────────────────────────────── */
.content {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 22px 26px 30px;
}

.page-enter-active,
.page-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-leave-to {
  opacity: 0;
}

@media (max-width: 1080px) {
  .sidebar {
    width: 74px;
    padding: 0 10px 14px;
  }
  .brand {
    justify-content: center;
    padding: 0;
  }
  .brand-text,
  .nav-label,
  .nav-group,
  .nav-tag,
  .secure-text {
    display: none;
  }
  .nav-item {
    justify-content: center;
    padding: 0;
  }
  .secure-card {
    justify-content: center;
    padding: 8px;
  }
  .content {
    padding: 18px;
  }
  .user-meta {
    display: none;
  }
}
</style>
