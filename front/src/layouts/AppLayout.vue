<template>
  <el-container class="app-layout">
    <el-aside width="232px" class="aside">
      <div class="logo">
        <div class="logo-name">Lumos</div>
        <div class="logo-sub">契光鉴微</div>
      </div>
      <el-menu
        :default-active="activeMenu"
        :default-openeds="defaultOpeneds"
        class="side-menu"
      >
        <div class="menu-group">概览</div>
        <el-menu-item index="/dashboard" @click="nav('/dashboard')"><el-icon><Odometer /></el-icon><span>工作台</span></el-menu-item>
        <div class="menu-group">审查协作</div>
        <el-menu-item index="/analysis" @click="nav('/analysis')"><el-icon><Document /></el-icon><span>AI 审查</span></el-menu-item>
        <el-menu-item index="/approvals" @click="nav('/approvals')"><el-icon><Finished /></el-icon><span>审批队列</span></el-menu-item>
        <el-menu-item index="/consult" @click="nav('/consult')"><el-icon><ChatLineRound /></el-icon><span>法律助理</span></el-menu-item>
        <div class="menu-group">合同资产</div>
        <el-menu-item index="/reports" @click="nav('/reports')"><el-icon><Clock /></el-icon><span>合同库</span></el-menu-item>
        <div class="menu-group">治理与洞察</div>
        <el-menu-item index="/playbooks" @click="nav('/playbooks')"><el-icon><Notebook /></el-icon><span>审查标准</span></el-menu-item>
        <el-menu-item index="/mcp" @click="nav('/mcp')"><el-icon><MagicStick /></el-icon><span>知识与工具</span></el-menu-item>
      </el-menu>
      <section class="session-panel">
        <div class="session-head"><span>历史对话</span><el-button link type="primary" @click="nav('/consult')"><el-icon><Plus /></el-icon> 新建</el-button></div>
        <div v-if="consult.sessions.length" class="session-list">
          <button v-for="s in consult.sessions.slice(0, 5)" :key="s.id" class="session-row" :class="{ active: route.query.s === s.id }" @click="navSession(s.id)">
            <el-icon><ChatLineSquare /></el-icon><span :title="s.title">{{ s.title || '未命名会话' }}</span>
          </button>
        </div>
        <button v-else class="empty-session" @click="nav('/consult')">暂无历史对话<br><small>从新建对话开始咨询</small></button>
      </section>
    </el-aside>

    <el-container class="body">
      <el-header class="header">
        <div class="page-title">{{ route.meta?.title ?? '' }}</div>
        <div class="user">
          <el-icon class="user-icon"><User /></el-icon>
          <span class="username">{{ auth.user?.username ?? '...' }}</span>
          <el-button type="danger" text size="small" @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatLineRound,
  ChatLineSquare,
  Clock,
  Document,
  MagicStick,
  Notebook,
  Odometer,
  Finished,
  Plus,
  User,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useConsultStore } from '@/stores/consult'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const consult = useConsultStore()

// 顶级菜单与子项的激活态完全由本计算属性驱动, 不依赖 el-menu 的 router 模式,
// 避免 query 参数(/consult?s=xxx)无法被自动匹配为活动项的问题.
const activeMenu = computed(() => {
  if (route.path === '/consult' && route.query.s) {
    return `/consult?s=${route.query.s}`
  }
  return route.path
})

// 进入 /consult 时自动展开「智能咨询」子菜单
const defaultOpeneds = computed(() =>
  route.path.startsWith('/consult') ? ['consult'] : []
)

const nav = (path: string) => {
  if (route.path !== path) router.push(path)
}

const navSession = (id: string) => {
  router.push({ path: '/consult', query: { s: id } })
}

const handleLogout = () => {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  // 刷新页面后 token 仍在而用户信息为空时补拉一次
  if (auth.isLoggedIn() && !auth.user) {
    auth.fetchUser()
  }
  // 登录态下预取会话列表, 让侧栏「历史会话」子项即时可见
  if (auth.isLoggedIn()) {
    consult.fetchSessions()
  }
})
</script>

<style scoped>
.app-layout {
  height: 100vh;
}
.aside {
  background: var(--ink-950);
  border-right: 1px solid rgba(255,255,255,.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.logo {
  height: 88px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 2px;
  border-bottom: 1px solid rgba(255,255,255,.1);
  flex-shrink: 0;
}
.logo-name {
  font-size: 22px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 0.5px;
}
.logo-sub {
  font-size: 12px;
  color: #9fb2cc;
  letter-spacing: 6px;
  transform: translateX(3px);
}
.side-menu {
  --el-menu-bg-color: var(--ink-950);
  --el-menu-text-color: #b9c9da;
  --el-menu-active-color: #ffffff;
  border-right: none;
  flex: 1 1 auto;
  padding: 14px 10px 0;
  overflow-y: auto;
  scrollbar-width: thin;
}
.session-panel { margin: 12px 14px 16px; border: 1px solid rgba(169,193,220,.2); border-radius: 10px; padding: 12px; color:#dbe8f8; background:rgba(255,255,255,.025); flex-shrink:0; }
.session-head { display:flex; justify-content:space-between; align-items:center; font-size:12px; color:#aebfd2; margin-bottom:8px; }.session-head .el-button{padding:0}
.session-list{display:grid;gap:3px}.session-row,.empty-session{border:0;background:transparent;color:#dbe8f8;text-align:left;width:100%;border-radius:6px;padding:8px;cursor:pointer;font:inherit}.session-row{display:flex;gap:8px;align-items:center}.session-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session-row:hover,.session-row.active{background:rgba(92,139,220,.22)}.empty-session{text-align:center;color:#9fb2cc;line-height:1.7}.empty-session small{font-size:11px}
.side-menu .el-menu-item {
  margin: 3px 0;
  border-radius: 6px;
  height: 38px;
  line-height: 38px;
}
.menu-group { padding: 13px 12px 5px; color: #7188a2; font-size: 10px; font-weight: 700; letter-spacing: 1.1px; line-height: 1; }
.side-menu .el-menu-item.is-active {
  background: #1d4ed8;
  color: #ffffff;
  font-weight: 500;
}
/* 子菜单内的项: 去掉外侧 8px 边距, 依靠 EP 自带的缩进对齐 */
.side-menu .el-sub-menu .el-menu-item {
  margin-left: 4px;
  margin-right: 8px;
}
/* 智能咨询标题在子项激活时高亮 (EP 会自动加 is-active) */
.side-menu .el-sub-menu.is-active > .el-sub-menu__title {
  color: #409eff;
}
/* 历史会话子项: 标题过长省略, 鼠标悬停显示完整标题 */
.session-title {
  display: inline-block;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.body {
  min-width: 0;
}
.header {
  height: 64px;
  background: #ffffff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
}
.page-title {
  font-size: 17px;
  font-weight: 600;
  color: #303133;
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-icon {
  color: #909399;
}
.username {
  color: #606266;
  font-size: 14px;
}
.main {
  background: var(--canvas);
  padding: 28px 32px;
  overflow-y: auto;
}
</style>
